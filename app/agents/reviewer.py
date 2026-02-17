"""
Main PR review agent orchestrator.

Coordinates the entire review process: fetching diffs, running static analysis,
invoking the LLM, evaluating confidence, and optionally refining the review.
"""

import logging
from typing import Dict, Any, Optional, List
import json

from app.config import Settings
from app.github.client import GitHubClient
from app.llm.model import LLMClient
from app.llm.prompts import (
    SYSTEM_PROMPT,
    build_review_prompt,
    build_refinement_prompt,
)
from app.llm.schemas import CodeReview, ReviewRecommendation, Finding, InlineComment
from app.agents.tools import ToolRegistry, ToolType
from app.agents.confidence import ConfidenceEvaluator, ConfidenceFactors

logger = logging.getLogger(__name__)


class ReviewContext:
    """Container for review context and intermediate results."""
    
    def __init__(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        pr_info: Dict[str, Any],
        installation_id: int,
    ):
        self.owner = owner
        self.repo = repo
        self.pr_number = pr_number
        self.pr_info = pr_info
        self.installation_id = installation_id
        
        # Intermediate results
        self.diff_info: Optional[Dict] = None
        self.static_analysis: Optional[Dict] = None
        self.risk_signals: Optional[Dict] = None
        self.file_context: Optional[Dict[str, str]] = None
        
        # Review results
        self.review: Optional[CodeReview] = None
        self.confidence_evaluation: Optional[Dict] = None
        self.iterations: int = 0


class PRReviewer:
    """
    Main PR review agent.
    
    Orchestrates the review process through multiple iterations if needed,
    combining static analysis with LLM-based review.
    """
    
    def __init__(
        self,
        settings: Settings,
        github_client: GitHubClient,
        llm_client: LLMClient,
    ):
        """
        Initialize PR reviewer.
        
        Args:
            settings: Application settings
            github_client: GitHub API client
            llm_client: LLM client for review generation
        """
        self.settings = settings
        self.github_client = github_client
        self.llm_client = llm_client
        self.tools = ToolRegistry(github_client)
        self.confidence_evaluator = ConfidenceEvaluator(
            confidence_threshold=settings.AGENT_CONFIDENCE_THRESHOLD
        )
    
    async def review_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        pr_info: Dict[str, Any],
        installation_id: int,
    ) -> Dict[str, Any]:
        """
        Execute complete PR review.
        
        This is the main entry point that orchestrates the entire review process.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            pr_info: PR metadata (title, description, author, etc.)
        
        Returns:
            Complete review result with recommendation and confidence
        """
        logger.info(f"Starting review for {owner}/{repo}#{pr_number}")
        
        # Initialize context
        context = ReviewContext(owner, repo, pr_number, pr_info, installation_id)

        
        try:
            # Step 1: Fetch and analyze PR
            await self._fetch_pr_data(context)
            
            # Step 2: Run static analysis
            await self._run_static_analysis(context)
            
            # Step 3: Generate initial review
            await self._generate_review(context)
            
            # Step 4: Evaluate confidence
            await self._evaluate_confidence(context)
            
            # Step 5: Refine if needed and iterations available
            await self._refine_if_needed(context)
            
            # Step 6: Finalize recommendation
            # Step 6: Finalize recommendation
            final_result = self._finalize_review(context)

            logger.info(
                f"Review complete: {final_result['recommendation']} "
                f"(confidence: {final_result['confidence']:.2f}, "
                f"iterations: {context.iterations})"
            )

            
            await self._publish_review(context, final_result)

            return final_result

            
        except Exception as e:
            logger.error(f"Review failed: {e}", exc_info=True)
            raise
    
    async def _fetch_pr_data(self, context: ReviewContext) -> None:
        """Fetch PR data from GitHub."""
        try:
            logger.info("Fetching PR data...")
            
            diff_result = await self.tools.execute_tool(
                ToolType.DIFF_FETCH,
                owner=context.owner,
                repo=context.repo,
                pr_number=context.pr_number,
                installation_id=context.installation_id,
            )
            
            if not diff_result.success:
                raise Exception(f"Diff fetch failed: {diff_result.error}")
            
            # Store diff info - it's a PRDiff object, not a dict
            context.diff_info = diff_result.data
            logger.info(
                "Diff info stored",
                extra={"diff_object_type": type(context.diff_info).__name__}
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch PR data: {e}", exc_info=True)
            raise
    
    async def _run_static_analysis(self, context: ReviewContext) -> None:
        """Run static analysis tools on changed files."""
        logger.info("Running static analysis...")
        
        # Get file contents for analysis
        # For now, we'll extract from the diff
        # In a full implementation, we'd fetch actual file contents
        file_contents = self._extract_file_contents_from_diff(context.diff_info)
        
        if not file_contents:
            logger.warning("No file contents available for static analysis")
            context.static_analysis = {}
            return
        
        # Run all static analysis tools
        context.static_analysis = await self.tools.execute_static_analysis(
            file_contents
        )
        
        total_issues = sum(
            len(results.get("issues", []))
            for results in context.static_analysis.values()
        )
        logger.info(f"Static analysis complete: {total_issues} issues found")
    
    async def _generate_review(self, context: ReviewContext) -> None:
        """Generate LLM-based review."""
        logger.info(f"Generating review (iteration {context.iterations + 1})...")
        
        try:
            # Access PRDiff attributes correctly
            diff_content = getattr(context.diff_info, 'unified_diff', '') or getattr(context.diff_info, 'raw_diff', '')
            
            user_prompt = build_review_prompt(
                pr_title=context.pr_info.get("title", ""),
                pr_description=context.pr_info.get("description", ""),
                diff_content=diff_content,
                static_analysis_results=context.static_analysis,
                risk_signals=context.risk_signals,
                file_context=context.file_context,
            )
            
            # Call LLM - it returns a CodeReview object directly
            context.review = await self.llm_client.generate_review(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            
            logger.info(
                "Review generated successfully",
                extra={
                    "risk_score": context.review.risk_score,
                    "recommendation": context.review.recommendation.value,
                    "findings_count": len(context.review.findings),
                }
            )
            
        except Exception as e:
            logger.error(f"Review generation failed: {e}", exc_info=True)
            raise
    
    async def _evaluate_confidence(self, context: ReviewContext) -> None:
        """Evaluate confidence in the generated review."""
        logger.info("Evaluating confidence...")
        
        eval_context = {
            "pr_info": context.pr_info,
            "diff_info": context.diff_info,
            "static_analysis": context.static_analysis,
            "file_context": context.file_context,
        }
        
        context.confidence_evaluation = self.confidence_evaluator.evaluate(
            context.review,
            eval_context,
        )
        
        logger.info(
            f"Confidence: {context.confidence_evaluation.overall_score:.2f}, "
            f"level: {context.confidence_evaluation.level}"
        )
        
    async def _publish_review(self, context: ReviewContext, result: Dict[str, Any]) -> None:
        """Publish review to GitHub."""
        logger.info("Publishing review to GitHub...")
        try:
            # Validate review exists
            if not context.review:
                logger.error("No review generated to publish")
                return
            
            if not context.diff_info:
                logger.error("No diff info available for publishing")
                return
            
            # Extract commit SHA from PRDiff object (not dict)
            # Assuming PRDiff has 'head_sha' attribute
            commit_id = getattr(context.diff_info, 'head_sha', None) or getattr(context.diff_info, 'sha', None)
            if not commit_id:
                logger.error(
                    "Missing commit SHA in diff_info",
                    extra={"diff_info_attrs": dir(context.diff_info)}
                )
                return
            
            # Convert review to markdown
            review_body = context.review.to_markdown() if hasattr(context.review, 'to_markdown') else str(context.review)
            
            # Determine review event from recommendation
            recommendation = result.get("recommendation")
            if not recommendation:
                logger.error("No recommendation in result")
                return
            
            event = recommendation.value if hasattr(recommendation, 'value') else str(recommendation)
            
            logger.info(
                f"Posting review with event: {event}",
                extra={
                    "pr": f"{context.owner}/{context.repo}#{context.pr_number}",
                    "commit_id": commit_id,
                }
            )
            
            # Create review on GitHub
            response = self.github_client.create_review(
                owner=context.owner,
                repo=context.repo,
                pr_number=context.pr_number,
                commit_id=commit_id,
                body=review_body,
                event=event,
                installation_id=context.installation_id,
            )
            
            logger.info(
                "Review successfully published to GitHub",
                extra={
                    "pr": f"{context.owner}/{context.repo}#{context.pr_number}",
                    "review_id": response.get("id"),
                    "recommendation": event,
                }
            )
            
        except Exception as e:
            logger.error(
                f"Failed to publish review: {e}",
                exc_info=True,
                extra={
                    "pr": f"{context.owner}/{context.repo}#{context.pr_number}",
                }
            )
            raise
    
    async def _refine_if_needed(self, context: ReviewContext) -> None:
        """Refine review if confidence is low and iterations remain."""
        
        if context.iterations >= self.settings.AGENT_MAX_ITERATIONS:
            logger.info("Max iterations reached, skipping refinement")
            return
        
        confidence = context.confidence_evaluation.overall_score
        if confidence >= self.settings.AGENT_CONFIDENCE_THRESHOLD:
            logger.info("Confidence threshold met, skipping refinement")
            return
        
        logger.info(f"Low confidence ({confidence:.2f}), attempting refinement...")
        
        # For now, skip refinement - simplified version
        # In full implementation, would improve uncertain areas
        logger.info("Refinement skipped in Phase 1")
    
    def _generate_refinement_feedback(
        self,
        context: ReviewContext,
        uncertain_areas: List[str],
    ) -> str:
        """Generate feedback for refinement."""
        feedback_parts = [
            "Please refine your review focusing on the following areas:",
        ]
        
        for area in uncertain_areas:
            feedback_parts.append(f"- {area}")
        
        return "\n".join(feedback_parts)
    
    

    
    def _finalize_review(self, context: ReviewContext) -> Dict[str, Any]:
        """Finalize and package the review result."""
        
        # Ensure recommendation aligns with review
        recommendation = context.review.recommendation
        
        return {
            "review": context.review,
            "recommendation": recommendation,
            "confidence": context.confidence_evaluation.overall_score,
            "confidence_level": context.confidence_evaluation.level,
            "iterations": context.iterations,
            "static_analysis_summary": self._summarize_static_analysis(
                context.static_analysis
            ),
            "risk_signals": context.risk_signals,
        }
    
    def _summarize_static_analysis(
        self,
        static_analysis: Optional[Dict],
    ) -> Dict[str, int]:
        """Summarize static analysis results."""
        if not static_analysis:
            return {}
        
        summary = {}
        for tool, results in static_analysis.items():
            if isinstance(results, dict) and "issues" in results:
                summary[tool] = len(results["issues"])
        
        return summary
    
    def _extract_file_contents_from_diff(
        self,
        diff_info: Dict,
    ) -> Dict[str, str]:
        """
        Extract file contents from diff for static analysis.
        
        Note: This is a simplified version. In production, we'd fetch
        actual file contents from the PR head ref.
        """
        # For now, return empty dict
        # Full implementation would use FileFetchTool
        return {}