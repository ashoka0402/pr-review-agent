"""
Risk detector module.

Detects potential risks in PRs using heuristics:
- Large diffs
- Critical file changes
- High complexity changes
- Breaking change patterns
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from app.config import settings
from app.github.diff_fetcher import PRDiff, FileChange
from app.analysis.diff_parser import FileDiff

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskFinding:
    """Represents a detected risk."""
    risk_type: str
    level: RiskLevel
    message: str
    affected_files: List[str]
    details: Optional[Dict[str, Any]] = None


class RiskDetector:
    """
    Detects potential risks in pull requests using heuristics.
    
    Risk categories:
    - Size risks (large diffs)
    - Critical file changes
    - Breaking change patterns
    - Configuration changes
    - Database migration risks
    """
    
    # Critical file patterns from config
    CRITICAL_PATTERNS = settings.CRITICAL_FILE_PATTERNS
    
    # Breaking change patterns
    BREAKING_PATTERNS = [
        r'def\s+\w+\([^)]*\)\s*->',  # Python function signature change
        r'class\s+\w+\([^)]*\):',     # Python class inheritance change
        r'function\s+\w+\([^)]*\)',   # JavaScript function signature
        r'interface\s+\w+\s*{',       # TypeScript interface
        r'type\s+\w+\s*=',            # TypeScript type alias
        r'public\s+\w+\s+\w+\(',      # Java public method
    ]
    
    # Database migration keywords
    DB_MIGRATION_KEYWORDS = [
        'DROP TABLE',
        'DROP COLUMN',
        'ALTER TABLE',
        'RENAME COLUMN',
        'CREATE INDEX',
        'DROP INDEX',
    ]
    
    # Security-sensitive patterns
    SECURITY_PATTERNS = [
        r'password',
        r'secret',
        r'api[_-]?key',
        r'token',
        r'auth',
        r'credential',
        r'\.env',
    ]
    
    def __init__(self):
        """Initialize risk detector."""
        self.findings: List[RiskFinding] = []
    
    def detect_risks(self, pr_diff: PRDiff) -> List[RiskFinding]:
        """
        Detect all risks in a PR.
        
        Args:
            pr_diff: PR diff data
        
        Returns:
            List[RiskFinding]: Detected risks
        """
        self.findings = []
        
        # Detect size-based risks
        self._detect_size_risks(pr_diff)
        
        # Detect critical file changes
        self._detect_critical_file_risks(pr_diff)
        
        # Detect configuration changes
        self._detect_configuration_risks(pr_diff)
        
        # Detect database migration risks
        self._detect_database_risks(pr_diff)
        
        # Detect security-sensitive changes
        self._detect_security_risks(pr_diff)
        
        logger.info(
            "Risk detection completed",
            extra={
                "total_findings": len(self.findings),
                "by_level": self._count_by_level(),
            }
        )
        
        return self.findings
    
    def _detect_size_risks(self, pr_diff: PRDiff):
        """
        Detect risks based on PR size.
        
        Args:
            pr_diff: PR diff data
        """
        # Very large PR
        if pr_diff.size_category == "very_large":
            self.findings.append(RiskFinding(
                risk_type="large_pr",
                level=RiskLevel.HIGH,
                message=f"Very large PR with {pr_diff.total_changes} line changes. "
                        f"Consider splitting into smaller PRs for easier review.",
                affected_files=[],
                details={
                    "total_changes": pr_diff.total_changes,
                    "files_changed": pr_diff.files_changed,
                }
            ))
        
        # Large number of files changed
        if pr_diff.files_changed > 20:
            self.findings.append(RiskFinding(
                risk_type="many_files",
                level=RiskLevel.MEDIUM,
                message=f"PR modifies {pr_diff.files_changed} files. "
                        f"High complexity may make review challenging.",
                affected_files=[],
                details={
                    "files_changed": pr_diff.files_changed,
                }
            ))
        
        # Individual large file changes
        for file_change in pr_diff.file_changes:
            if file_change.changes > 300:
                self.findings.append(RiskFinding(
                    risk_type="large_file_change",
                    level=RiskLevel.MEDIUM,
                    message=f"Large changes in single file ({file_change.changes} lines)",
                    affected_files=[file_change.filename],
                    details={
                        "changes": file_change.changes,
                        "additions": file_change.additions,
                        "deletions": file_change.deletions,
                    }
                ))
    
    def _detect_critical_file_risks(self, pr_diff: PRDiff):
        """
        Detect changes to critical files.
        
        Args:
            pr_diff: PR diff data
        """
        critical_files = []
        
        for file_change in pr_diff.file_changes:
            if self._is_critical_file(file_change.filename):
                critical_files.append(file_change.filename)
        
        if critical_files:
            self.findings.append(RiskFinding(
                risk_type="critical_files",
                level=RiskLevel.HIGH,
                message=f"Changes to {len(critical_files)} critical file(s). "
                        f"Extra review attention required.",
                affected_files=critical_files,
                details={
                    "file_count": len(critical_files),
                }
            ))
    
    def _is_critical_file(self, filepath: str) -> bool:
        """
        Check if a file is critical based on patterns.
        
        Args:
            filepath: File path
        
        Returns:
            bool: True if file is critical
        """
        for pattern in self.CRITICAL_PATTERNS:
            # Convert glob pattern to regex
            regex_pattern = pattern.replace('*', '.*').replace('?', '.')
            if re.search(regex_pattern, filepath, re.IGNORECASE):
                return True
        
        return False
    
    def _detect_configuration_risks(self, pr_diff: PRDiff):
        """
        Detect configuration file changes.
        
        Args:
            pr_diff: PR diff data
        """
        config_extensions = [
            '.yaml', '.yml', '.json', '.toml', '.ini', '.conf',
            '.env', '.config'
        ]
        
        config_files = []
        
        for file_change in pr_diff.file_changes:
            filename = file_change.filename.lower()
            
            # Check extension
            if any(filename.endswith(ext) for ext in config_extensions):
                config_files.append(file_change.filename)
            
            # Check special config files
            elif any(name in filename for name in [
                'dockerfile', 'docker-compose', '.dockerignore',
                'nginx.conf', 'package.json', 'requirements.txt'
            ]):
                config_files.append(file_change.filename)
        
        if config_files:
            self.findings.append(RiskFinding(
                risk_type="configuration_changes",
                level=RiskLevel.MEDIUM,
                message=f"Configuration files modified. Verify changes carefully.",
                affected_files=config_files,
                details={
                    "config_files": len(config_files),
                }
            ))
    
    def _detect_database_risks(self, pr_diff: PRDiff):
        """
        Detect database migration risks.
        
        Args:
            pr_diff: PR diff data
        """
        migration_files = []
        risky_migrations = []
        
        for file_change in pr_diff.file_changes:
            filename = file_change.filename.lower()
            
            # Check if it's a migration file
            if any(keyword in filename for keyword in [
                'migration', 'migrate', 'schema', 'alembic', 'flyway'
            ]):
                migration_files.append(file_change.filename)
                
                # Check for risky SQL operations
                if file_change.patch:
                    patch_upper = file_change.patch.upper()
                    for keyword in self.DB_MIGRATION_KEYWORDS:
                        if keyword in patch_upper:
                            risky_migrations.append({
                                'file': file_change.filename,
                                'operation': keyword,
                            })
        
        if migration_files:
            level = RiskLevel.HIGH if risky_migrations else RiskLevel.MEDIUM
            
            self.findings.append(RiskFinding(
                risk_type="database_migration",
                level=level,
                message=f"Database migration detected. "
                        f"{'Potentially destructive operations found. ' if risky_migrations else ''}"
                        f"Ensure backward compatibility and rollback plan.",
                affected_files=migration_files,
                details={
                    "migration_count": len(migration_files),
                    "risky_operations": risky_migrations,
                }
            ))
    
    def _detect_security_risks(self, pr_diff: PRDiff):
        """
        Detect security-sensitive changes.
        
        Args:
            pr_diff: PR diff data
        """
        security_files = []
        
        for file_change in pr_diff.file_changes:
            filename = file_change.filename.lower()
            
            # Check filename for security patterns
            for pattern in self.SECURITY_PATTERNS:
                if re.search(pattern, filename, re.IGNORECASE):
                    security_files.append(file_change.filename)
                    break
            
            # Check patch content for security patterns
            if file_change.patch:
                for pattern in self.SECURITY_PATTERNS:
                    if re.search(pattern, file_change.patch, re.IGNORECASE):
                        if file_change.filename not in security_files:
                            security_files.append(file_change.filename)
                        break
        
        if security_files:
            self.findings.append(RiskFinding(
                risk_type="security_sensitive",
                level=RiskLevel.HIGH,
                message=f"Security-sensitive changes detected. "
                        f"Verify no credentials or secrets are exposed.",
                affected_files=security_files,
                details={
                    "affected_files": len(security_files),
                }
            ))
    
    def detect_breaking_changes(self, file_diffs: List[FileDiff]) -> List[RiskFinding]:
        """
        Detect potential breaking changes in code.
        
        Args:
            file_diffs: Parsed file diffs
        
        Returns:
            List[RiskFinding]: Breaking change findings
        """
        breaking_findings = []
        
        for file_diff in file_diffs:
            if not file_diff.language:
                continue
            
            # Check removed lines for breaking patterns
            for hunk in file_diff.hunks:
                for line in hunk.lines:
                    if line.change_type.value == "removed":
                        for pattern in self.BREAKING_PATTERNS:
                            if re.search(pattern, line.content):
                                breaking_findings.append(RiskFinding(
                                    risk_type="breaking_change",
                                    level=RiskLevel.HIGH,
                                    message=f"Potential breaking change: "
                                            f"signature or interface modification",
                                    affected_files=[file_diff.filename],
                                    details={
                                        "pattern": pattern,
                                        "line": line.content.strip(),
                                    }
                                ))
                                break
        
        self.findings.extend(breaking_findings)
        return breaking_findings
    
    def calculate_overall_risk_score(self) -> float:
        """
        Calculate overall risk score from findings.
        
        Score: 0.0 (low risk) to 1.0 (critical risk)
        
        Returns:
            float: Risk score
        """
        if not self.findings:
            return 0.0
        
        # Weight by risk level
        level_weights = {
            RiskLevel.LOW: 0.1,
            RiskLevel.MEDIUM: 0.3,
            RiskLevel.HIGH: 0.6,
            RiskLevel.CRITICAL: 1.0,
        }
        
        total_score = sum(
            level_weights[finding.level]
            for finding in self.findings
        )
        
        # Normalize by number of findings (with dampening)
        score = min(total_score / (len(self.findings) * 0.5), 1.0)
        
        return round(score, 2)
    
    def get_recommendation(self) -> str:
        """
        Get review recommendation based on risk findings.
        
        Returns:
            str: Recommendation (APPROVE, COMMENT, REQUEST_CHANGES)
        """
        risk_score = self.calculate_overall_risk_score()
        
        # Check for critical findings
        has_critical = any(
            finding.level == RiskLevel.CRITICAL
            for finding in self.findings
        )
        
        # Check for high-risk findings
        high_risk_count = sum(
            1 for finding in self.findings
            if finding.level == RiskLevel.HIGH
        )
        
        if has_critical or high_risk_count >= 3:
            return "REQUEST_CHANGES"
        elif risk_score > 0.5 or high_risk_count > 0:
            return "COMMENT"
        else:
            return "APPROVE"
    
    def _count_by_level(self) -> Dict[str, int]:
        """
        Count findings by risk level.
        
        Returns:
            Dict[str, int]: Level -> count mapping
        """
        counts = {level.value: 0 for level in RiskLevel}
        
        for finding in self.findings:
            counts[finding.level.value] += 1
        
        return counts
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of risk findings.
        
        Returns:
            Dict: Risk summary
        """
        return {
            "total_findings": len(self.findings),
            "risk_score": self.calculate_overall_risk_score(),
            "recommendation": self.get_recommendation(),
            "by_level": self._count_by_level(),
            "by_type": self._count_by_type(),
            "critical_files": self._get_critical_files(),
        }
    
    def _count_by_type(self) -> Dict[str, int]:
        """
        Count findings by risk type.
        
        Returns:
            Dict[str, int]: Type -> count mapping
        """
        counts = {}
        
        for finding in self.findings:
            counts[finding.risk_type] = counts.get(finding.risk_type, 0) + 1
        
        return counts
    
    def _get_critical_files(self) -> List[str]:
        """
        Get list of all critical files from findings.
        
        Returns:
            List[str]: Critical file paths
        """
        critical_files = set()
        
        for finding in self.findings:
            if finding.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                critical_files.update(finding.affected_files)
        
        return sorted(list(critical_files))