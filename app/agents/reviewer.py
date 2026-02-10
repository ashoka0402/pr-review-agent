"""
Main PR review agent orchestrator.

Coordinates the entire review process: fetching diffs, running static analysis,
invoking the LLM, evaluating confidence, and optionally refining the review.
"""

import logging
from typing import Dict, Any, Optional, List

from app.config import Settings
from app.github.client import GitHubClient
from app.llm.model import LLMClient
from app.llm.prompts import (
    SYSTEM_PROMPT,
    build_review_prompt,
    build_refinement_prompt,
)
from app.llm.schemas import CodeReview, ReviewRecommendation
from app.agent.tools import ToolRegistry, ToolType
from app.agent.confidence import ConfidenceEvaluator, ConfidenceFactors

logger = logging.getLogger(__name__)


class ReviewContext:
    """Container for review context and intermediate results."""
    
    def __init__(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        pr_info: Dict[str, Any],
    ):
        self.owner = owner
        self.repo = repo
        self.pr_number = pr_number
        self.pr_info = pr_info
        
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
        context = ReviewContext(owner, repo, pr_number, pr_info)
        
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
            final_result = self._finalize_review(context)
            
            logger.info(
                f"Review complete: {final_result['recommendation']} "
                f"(confidence: {final_result['confidence']:.2f}, "
                f"iterations: {context.iterations})"
            )
            
            return final_result
            
        except Exception as e:
            logger.error(f"Review failed: {e}", exc_info=True)
            raise
    
    async def _fetch_pr_data(self, context: ReviewContext) -> None:
        """Fetch PR diff and metadata."""
        logger.info("Fetching PR data...")
        
        # Fetch diff
        diff_result = await self.tools.execute_tool(
            ToolType.DIFF_FETCH,
            owner=context.owner,
            repo=context.repo,
            pr_number=context.pr_number,
        )
        
        if not diff_result.success:
            raise Exception(f"Failed to fetch diff: {diff_result.error}")
        
        context.diff_info = diff_result.data
        logger.info(
            f"Fetched diff: {context.diff_info['total_changes']} lines, "
            f"{len(context.diff_info['files'])} files"
        )
        
        # Detect risks
        risk_result = await self.tools.execute_tool(
            ToolType.RISK_DETECTION,
            diff_content=context.diff_info["diff"],
            file_paths=context.diff_info["files"],
            lines_changed=context.diff_info["total_changes"],
        )
        
        if risk_result.success:
            context.risk_signals = risk_result.data
            logger.info(f"Risk signals: {context.risk_signals}")
    
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
        
        # Build prompt
        user_prompt = build_review_prompt(
            pr_title=context.pr_info.get("title", ""),
            pr_description=context.pr_info.get("description"),
            diff_content=context.diff_info["diff"],
            static_analysis_results=context.static_analysis,
            risk_signals=context.risk_signals,
            file_context=context.file_context,
        )
        
        # Generate review
        context.review = await self.llm_client.generate_review(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.0,  # Deterministic
        )
        
        context.iterations += 1
        logger.info(
            f"Generated review with {len(context.review.comments)} comments, "
            f"recommendation: {context.review.recommendation}"
        )
    
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
            f"Confidence: {context.confidence_evaluation['overall_confidence']:.2f}, "
            f"needs_human: {context.confidence_evaluation['needs_human_review']}"
        )
    
    async def _refine_if_needed(self, context: ReviewContext) -> None:
        """Refine review if confidence is low and iterations remain."""
        
        if context.iterations >= self.settings.AGENT_MAX_ITERATIONS:
            logger.info("Max iterations reached, skipping refinement")
            return
        
        confidence = context.confidence_evaluation["overall_confidence"]
        if confidence >= self.settings.AGENT_CONFIDENCE_THRESHOLD:
            logger.info("Confidence threshold met, skipping refinement")
            return
        
        logger.info(f"Low confidence ({confidence:.2f}), attempting refinement...")
        
        # Identify what to improve
        uncertain_areas = context.confidence_evaluation.get("uncertain_areas", [])
        feedback = self._generate_refinement_feedback(context, uncertain_areas)
        
        # Build refinement prompt
        refinement_prompt = build_refinement_prompt(
            original_review=context.review.model_dump(),
            feedback=feedback,
            iteration=context.iterations,
        )
        
        # Generate refined review
        try:
            refined_review = await self.llm_client.generate_review(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=refinement_prompt,
                temperature=0.1,  # Slightly more creative for refinement
            )
            
            context.review = refined_review
            context.iterations += 1
            
            # Re-evaluate confidence
            await self._evaluate_confidence(context)
            
            logger.info(
                f"Refinement complete. New confidence: "
                f"{context.confidence_evaluation['overall_confidence']:.2f}"
            )
            
        except Exception as e:
            logger.error(f"Refinement failed: {e}")
            # Keep original review
    
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
        
        # Add specific guidance based on review characteristics
        if len(context.review.comments) < 3 and context.diff_info["total_changes"] > 100:
            feedback_parts.append(
                "- Consider adding more detailed comments for this large PR"
            )
        
        if context.review.has_blocking_issues():
            critical_comments = [
                c for c in context.review.comments
                if c.severity.value in ["critical", "error"]
            ]
            low_confidence = [c for c in critical_comments if c.confidence < 0.8]
            if low_confidence:
                feedback_parts.append(
                    f"- Verify {len(low_confidence)} critical/error comments with low confidence"
                )
        
        return "\n".join(feedback_parts)
    
    def _finalize_review(self, context: ReviewContext) -> Dict[str, Any]:
        """Finalize and package the review result."""
        
        # Ensure recommendation aligns with issues
        recommendation = self._determine_final_recommendation(context.review)
        
        return {
            "review": context.review,
            "recommendation": recommendation,
            "confidence": context.confidence_evaluation["overall_confidence"],
            "needs_human_review": context.confidence_evaluation["needs_human_review"],
            "reasoning": context.confidence_evaluation["reasoning"],
            "uncertain_areas": context.confidence_evaluation["uncertain_areas"],
            "iterations": context.iterations,
            "static_analysis_summary": self._summarize_static_analysis(
                context.static_analysis
            ),
            "risk_signals": context.risk_signals,
        }
    
    def _determine_final_recommendation(
        self,
        review: CodeReview,
    ) -> ReviewRecommendation:
        """
        Determine final recommendation based on issues.
        
        Enforces logic: CRITICAL/ERROR issues → REQUEST_CHANGES
        """
        if review.has_blocking_issues():
            return ReviewRecommendation.REQUEST_CHANGES
        
        if len(review.comments) == 0:
            return ReviewRecommendation.APPROVE
        
        # Return the LLM's recommendation for non-blocking cases
        return review.recommendation
    
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