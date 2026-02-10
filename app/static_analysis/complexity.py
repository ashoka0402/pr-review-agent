"""
Complexity analyzer module.

Analyzes code complexity metrics:
- Cyclomatic complexity
- Maintainability index
- Code metrics for each function/method
"""

import subprocess
import json
import logging
import tempfile
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FunctionComplexity:
    """Complexity metrics for a single function."""
    name: str
    line_number: int
    cyclomatic_complexity: int
    rank: str  # A (simple), B, C, D, E, F (very complex)


@dataclass
class FileComplexity:
    """Complexity metrics for a file."""
    file: str
    average_complexity: float
    total_lines: int
    functions: List[FunctionComplexity]
    maintainability_index: Optional[float] = None


class ComplexityAnalyzer:
    """
    Analyzes code complexity using various metrics.
    
    Tools used:
    - radon for Python (cyclomatic complexity, maintainability)
    - eslint-plugin-complexity for JavaScript (optional)
    """
    
    def __init__(self):
        """Initialize complexity analyzer."""
        self.results: List[FileComplexity] = []
    
    async def analyze(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ) -> List[FileComplexity]:
        """
        Run complexity analysis on files.
        
        Args:
            files: List of file metadata
            file_contents: Mapping of filename -> content
        
        Returns:
            List[FileComplexity]: Complexity results
        """
        if not settings.ENABLE_COMPLEXITY_ANALYSIS:
            logger.info("Complexity analysis is disabled")
            return []
        
        self.results = []
        
        # Group files by language
        python_files = [
            f for f in files 
            if f.get('language') == 'python' and f['filename'] in file_contents
        ]
        
        # Run Python complexity analysis
        if python_files:
            await self._analyze_python_complexity(python_files, file_contents)
        
        logger.info(
            "Complexity analysis completed",
            extra={
                "files_analyzed": len(self.results),
                "complex_functions": len(self.get_complex_functions()),
            }
        )
        
        return self.results
    
    async def _analyze_python_complexity(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ):
        """
        Analyze Python code complexity using radon.
        
        Args:
            files: List of Python file metadata
            file_contents: File contents mapping
        """
        # Create temporary directory for files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write files to temp directory
            temp_files = []
            for file_meta in files:
                filename = file_meta['filename']
                if filename not in file_contents:
                    continue
                
                # Create file path
                temp_path = os.path.join(tmpdir, os.path.basename(filename))
                
                with open(temp_path, 'w') as f:
                    f.write(file_contents[filename])
                
                temp_files.append((temp_path, filename))
            
            if not temp_files:
                return
            
            # Run radon cc (cyclomatic complexity)
            cc_results = await self._run_radon_cc(temp_files)
            
            # Run radon mi (maintainability index)
            mi_results = await self._run_radon_mi(temp_files)
            
            # Combine results
            for temp_path, original_filename in temp_files:
                functions = cc_results.get(temp_path, [])
                maintainability = mi_results.get(temp_path)
                
                if functions or maintainability is not None:
                    avg_complexity = (
                        sum(f.cyclomatic_complexity for f in functions) / len(functions)
                        if functions else 0.0
                    )
                    
                    self.results.append(FileComplexity(
                        file=original_filename,
                        average_complexity=round(avg_complexity, 2),
                        total_lines=len(file_contents[original_filename].split('\n')),
                        functions=functions,
                        maintainability_index=maintainability,
                    ))
    
    async def _run_radon_cc(
        self,
        temp_files: List[tuple],
    ) -> Dict[str, List[FunctionComplexity]]:
        """
        Run radon cyclomatic complexity analysis.
        
        Args:
            temp_files: List of (temp_path, original_filename) tuples
        
        Returns:
            Dict[str, List[FunctionComplexity]]: Results by temp path
        """
        results = {}
        
        try:
            cmd = [
                'radon',
                'cc',
                '--json',
                '--min', 'A',  # Show all complexity levels
            ] + [path for path, _ in temp_files]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.stdout:
                try:
                    radon_data = json.loads(result.stdout)
                    
                    for temp_path, _ in temp_files:
                        abs_path = os.path.abspath(temp_path)
                        
                        if abs_path in radon_data:
                            functions = []
                            
                            for func_data in radon_data[abs_path]:
                                functions.append(FunctionComplexity(
                                    name=func_data['name'],
                                    line_number=func_data['lineno'],
                                    cyclomatic_complexity=func_data['complexity'],
                                    rank=func_data['rank'],
                                ))
                            
                            results[temp_path] = functions
                
                except json.JSONDecodeError:
                    logger.error("Failed to parse radon cc JSON output")
        
        except subprocess.TimeoutExpired:
            logger.warning("Radon cc timed out")
        except FileNotFoundError:
            logger.warning("Radon not installed")
        except Exception as e:
            logger.error(f"Radon cc error: {e}")
        
        return results
    
    async def _run_radon_mi(
        self,
        temp_files: List[tuple],
    ) -> Dict[str, float]:
        """
        Run radon maintainability index analysis.
        
        Args:
            temp_files: List of (temp_path, original_filename) tuples
        
        Returns:
            Dict[str, float]: Maintainability index by temp path
        """
        results = {}
        
        try:
            cmd = [
                'radon',
                'mi',
                '--json',
            ] + [path for path, _ in temp_files]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.stdout:
                try:
                    radon_data = json.loads(result.stdout)
                    
                    for temp_path, _ in temp_files:
                        abs_path = os.path.abspath(temp_path)
                        
                        if abs_path in radon_data:
                            mi_data = radon_data[abs_path]
                            
                            # MI can be a dict or a number
                            if isinstance(mi_data, dict):
                                mi = mi_data.get('mi', 0.0)
                            else:
                                mi = float(mi_data)
                            
                            results[temp_path] = round(mi, 2)
                
                except json.JSONDecodeError:
                    logger.error("Failed to parse radon mi JSON output")
        
        except subprocess.TimeoutExpired:
            logger.warning("Radon mi timed out")
        except FileNotFoundError:
            logger.warning("Radon not installed")
        except Exception as e:
            logger.error(f"Radon mi error: {e}")
        
        return results
    
    def get_complex_functions(
        self,
        threshold: Optional[int] = None,
    ) -> List[tuple]:
        """
        Get functions exceeding complexity threshold.
        
        Args:
            threshold: Complexity threshold (uses config default if None)
        
        Returns:
            List[tuple]: List of (file, function) tuples
        """
        if threshold is None:
            threshold = settings.CYCLOMATIC_COMPLEXITY_THRESHOLD
        
        complex_funcs = []
        
        for file_result in self.results:
            for func in file_result.functions:
                if func.cyclomatic_complexity > threshold:
                    complex_funcs.append((file_result.file, func))
        
        return complex_funcs
    
    def get_low_maintainability_files(
        self,
        threshold: Optional[int] = None,
    ) -> List[FileComplexity]:
        """
        Get files with low maintainability index.
        
        Args:
            threshold: MI threshold (uses config default if None)
        
        Returns:
            List[FileComplexity]: Files below threshold
        """
        if threshold is None:
            threshold = settings.MAINTAINABILITY_INDEX_THRESHOLD
        
        return [
            result for result in self.results
            if result.maintainability_index is not None
            and result.maintainability_index < threshold
        ]
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of complexity analysis.
        
        Returns:
            Dict: Complexity summary
        """
        complex_funcs = self.get_complex_functions()
        low_mi_files = self.get_low_maintainability_files()
        
        # Calculate overall statistics
        all_functions = []
        for result in self.results:
            all_functions.extend(result.functions)
        
        avg_complexity = (
            sum(f.cyclomatic_complexity for f in all_functions) / len(all_functions)
            if all_functions else 0.0
        )
        
        mi_values = [
            r.maintainability_index 
            for r in self.results 
            if r.maintainability_index is not None
        ]
        avg_mi = sum(mi_values) / len(mi_values) if mi_values else None
        
        return {
            "files_analyzed": len(self.results),
            "total_functions": len(all_functions),
            "average_complexity": round(avg_complexity, 2),
            "complex_functions_count": len(complex_funcs),
            "average_maintainability_index": round(avg_mi, 2) if avg_mi else None,
            "low_maintainability_files": len(low_mi_files),
            "complexity_threshold": settings.CYCLOMATIC_COMPLEXITY_THRESHOLD,
            "maintainability_threshold": settings.MAINTAINABILITY_INDEX_THRESHOLD,
        }
    
    def format_complexity_warning(
        self,
        file: str,
        func: FunctionComplexity,
    ) -> str:
        """
        Format a complexity warning for review.
        
        Args:
            file: File path
            func: Function complexity data
        
        Returns:
            str: Formatted warning message
        """
        msg = f"**High Complexity**: Function `{func.name}` has cyclomatic complexity of {func.cyclomatic_complexity} "
        msg += f"(rank {func.rank}). "
        msg += f"Consider refactoring to reduce complexity."
        
        return msg
    
    def format_maintainability_warning(
        self,
        file_result: FileComplexity,
    ) -> str:
        """
        Format a maintainability warning for review.
        
        Args:
            file_result: File complexity result
        
        Returns:
            str: Formatted warning message
        """
        mi = file_result.maintainability_index
        
        msg = f"**Low Maintainability**: This file has a maintainability index of {mi:.1f}. "
        
        if mi < 10:
            msg += "Code is extremely difficult to maintain."
        elif mi < 20:
            msg += "Code is difficult to maintain."
        else:
            msg += "Code maintainability could be improved."
        
        msg += " Consider refactoring or adding documentation."
        
        return msg