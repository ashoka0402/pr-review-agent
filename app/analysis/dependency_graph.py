"""
Dependency graph module.

Analyzes cross-file dependencies to understand:
- Which files import/depend on changed files
- Impact radius of changes
- Module coupling
"""

import re
import logging
from typing import Dict, List, Set, Optional
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ImportStatement:
    """Represents a single import statement."""
    source_file: str
    imported_module: str
    import_type: str  # 'import', 'from_import', 'require', etc.
    line_number: Optional[int] = None
    is_relative: bool = False


@dataclass
class FileDependency:
    """Represents dependencies for a single file."""
    filepath: str
    imports: List[ImportStatement]
    imported_by: List[str]  # Files that import this file
    imports_from: List[str]  # Files this file imports


class DependencyGraph:
    """
    Analyzes file dependencies and import relationships.
    
    Helps understand the impact radius of changes by tracking
    which files depend on modified files.
    """
    
    # Import pattern regex for different languages
    PYTHON_IMPORT_PATTERN = re.compile(
        r'^\s*(?:from\s+([\w\.]+)\s+)?import\s+([\w\.\*,\s]+)',
        re.MULTILINE
    )
    
    JAVASCRIPT_IMPORT_PATTERN = re.compile(
        r'^\s*import\s+(?:{[^}]+}|[\w]+)\s+from\s+[\'"]([^\'"]+)[\'"]',
        re.MULTILINE
    )
    
    JAVASCRIPT_REQUIRE_PATTERN = re.compile(
        r'^\s*(?:const|let|var)\s+[\w{},\s]+\s*=\s*require\([\'"]([^\'"]+)[\'"]\)',
        re.MULTILINE
    )
    
    def __init__(self):
        """Initialize dependency graph."""
        self.dependencies: Dict[str, FileDependency] = {}
        self.import_graph: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_graph: Dict[str, Set[str]] = defaultdict(set)
    
    def analyze_file_dependencies(
        self,
        filepath: str,
        file_content: str,
        language: Optional[str] = None,
    ) -> FileDependency:
        """
        Analyze dependencies in a single file.
        
        Args:
            filepath: Path to the file
            file_content: Content of the file
            language: Programming language (auto-detected if None)
        
        Returns:
            FileDependency: Parsed dependencies
        """
        if not language:
            language = self._detect_language(filepath)
        
        imports = []
        
        if language == 'python':
            imports = self._parse_python_imports(filepath, file_content)
        elif language in ['javascript', 'typescript']:
            imports = self._parse_javascript_imports(filepath, file_content)
        
        # Build dependency object
        file_dep = FileDependency(
            filepath=filepath,
            imports=imports,
            imported_by=[],
            imports_from=[imp.imported_module for imp in imports],
        )
        
        self.dependencies[filepath] = file_dep
        
        # Update import graph
        for imp in imports:
            self.import_graph[filepath].add(imp.imported_module)
            self.reverse_graph[imp.imported_module].add(filepath)
        
        logger.debug(
            "Analyzed file dependencies",
            extra={
                "filepath": filepath,
                "imports_count": len(imports),
            }
        )
        
        return file_dep
    
    def _parse_python_imports(
        self,
        filepath: str,
        content: str,
    ) -> List[ImportStatement]:
        """
        Parse Python import statements.
        
        Args:
            filepath: Source file path
            content: File content
        
        Returns:
            List[ImportStatement]: Parsed imports
        """
        imports = []
        
        for match in self.PYTHON_IMPORT_PATTERN.finditer(content):
            from_module = match.group(1)
            import_names = match.group(2)
            
            if from_module:
                # from X import Y
                imports.append(ImportStatement(
                    source_file=filepath,
                    imported_module=from_module,
                    import_type='from_import',
                    is_relative=from_module.startswith('.'),
                ))
            else:
                # import X
                for module in import_names.split(','):
                    module = module.strip()
                    if module and module != '*':
                        imports.append(ImportStatement(
                            source_file=filepath,
                            imported_module=module,
                            import_type='import',
                            is_relative=module.startswith('.'),
                        ))
        
        return imports
    
    def _parse_javascript_imports(
        self,
        filepath: str,
        content: str,
    ) -> List[ImportStatement]:
        """
        Parse JavaScript/TypeScript import statements.
        
        Args:
            filepath: Source file path
            content: File content
        
        Returns:
            List[ImportStatement]: Parsed imports
        """
        imports = []
        
        # ES6 imports
        for match in self.JAVASCRIPT_IMPORT_PATTERN.finditer(content):
            module = match.group(1)
            imports.append(ImportStatement(
                source_file=filepath,
                imported_module=module,
                import_type='import',
                is_relative=module.startswith('.'),
            ))
        
        # CommonJS requires
        for match in self.JAVASCRIPT_REQUIRE_PATTERN.finditer(content):
            module = match.group(1)
            imports.append(ImportStatement(
                source_file=filepath,
                imported_module=module,
                import_type='require',
                is_relative=module.startswith('.'),
            ))
        
        return imports
    
    def _detect_language(self, filepath: str) -> Optional[str]:
        """
        Detect language from file extension.
        
        Args:
            filepath: File path
        
        Returns:
            Optional[str]: Detected language
        """
        ext = filepath.split('.')[-1].lower()
        
        language_map = {
            'py': 'python',
            'js': 'javascript',
            'jsx': 'javascript',
            'ts': 'typescript',
            'tsx': 'typescript',
        }
        
        return language_map.get(ext)
    
    def get_impact_radius(
        self,
        changed_files: List[str],
        max_depth: int = 2,
    ) -> Dict[str, int]:
        """
        Calculate impact radius for changed files.
        
        Returns files that depend on changed files, with their depth.
        
        Args:
            changed_files: List of changed file paths
            max_depth: Maximum dependency depth to traverse
        
        Returns:
            Dict[str, int]: File path -> depth mapping
        """
        impact = {}
        visited = set()
        
        def traverse(file: str, depth: int):
            if depth > max_depth or file in visited:
                return
            
            visited.add(file)
            impact[file] = min(impact.get(file, depth), depth)
            
            # Get files that import this file
            for dependent in self.reverse_graph.get(file, []):
                traverse(dependent, depth + 1)
        
        # Start traversal from changed files
        for changed_file in changed_files:
            traverse(changed_file, 0)
        
        # Remove the changed files themselves
        for changed_file in changed_files:
            impact.pop(changed_file, None)
        
        logger.info(
            "Calculated impact radius",
            extra={
                "changed_files": len(changed_files),
                "impacted_files": len(impact),
            }
        )
        
        return impact
    
    def get_coupled_modules(
        self,
        filepath: str,
    ) -> List[str]:
        """
        Get modules tightly coupled with this file.
        
        Tight coupling = bidirectional imports.
        
        Args:
            filepath: File path to analyze
        
        Returns:
            List[str]: Tightly coupled module paths
        """
        coupled = []
        
        # Files this file imports
        imports = self.import_graph.get(filepath, set())
        
        # Files that import this file
        imported_by = self.reverse_graph.get(filepath, set())
        
        # Bidirectional = tight coupling
        coupled = list(imports & imported_by)
        
        return coupled
    
    def detect_circular_dependencies(
        self,
        start_file: str,
    ) -> List[List[str]]:
        """
        Detect circular dependencies starting from a file.
        
        Args:
            start_file: File to start detection from
        
        Returns:
            List[List[str]]: List of circular dependency paths
        """
        cycles = []
        visited = set()
        path = []
        
        def dfs(file: str):
            if file in path:
                # Found a cycle
                cycle_start = path.index(file)
                cycle = path[cycle_start:] + [file]
                cycles.append(cycle)
                return
            
            if file in visited:
                return
            
            visited.add(file)
            path.append(file)
            
            for imported in self.import_graph.get(file, []):
                dfs(imported)
            
            path.pop()
        
        dfs(start_file)
        
        return cycles
    
    def get_dependency_depth(self, filepath: str) -> int:
        """
        Get maximum dependency depth for a file.
        
        Depth = longest chain of imports from this file.
        
        Args:
            filepath: File path
        
        Returns:
            int: Maximum dependency depth
        """
        max_depth = 0
        visited = set()
        
        def dfs(file: str, depth: int):
            nonlocal max_depth
            
            if file in visited:
                return
            
            visited.add(file)
            max_depth = max(max_depth, depth)
            
            for imported in self.import_graph.get(file, []):
                dfs(imported, depth + 1)
        
        dfs(filepath, 0)
        
        return max_depth
    
    def get_external_dependencies(self, filepath: str) -> List[str]:
        """
        Get external (third-party) dependencies for a file.
        
        External = not relative imports.
        
        Args:
            filepath: File path
        
        Returns:
            List[str]: External module names
        """
        if filepath not in self.dependencies:
            return []
        
        file_dep = self.dependencies[filepath]
        external = [
            imp.imported_module 
            for imp in file_dep.imports 
            if not imp.is_relative
        ]
        
        return external
    
    def summarize_graph(self) -> Dict[str, any]:
        """
        Generate summary statistics for the dependency graph.
        
        Returns:
            Dict: Summary statistics
        """
        total_files = len(self.dependencies)
        total_imports = sum(len(deps.imports) for deps in self.dependencies.values())
        
        # Calculate coupling metrics
        coupling_scores = {}
        for filepath, deps in self.dependencies.items():
            # Coupling = number of imports + number of importers
            coupling = len(deps.imports) + len(self.reverse_graph.get(filepath, []))
            coupling_scores[filepath] = coupling
        
        # Find most coupled files
        most_coupled = sorted(
            coupling_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            'total_files': total_files,
            'total_imports': total_imports,
            'avg_imports_per_file': total_imports / total_files if total_files > 0 else 0,
            'most_coupled_files': [
                {'file': file, 'coupling_score': score}
                for file, score in most_coupled
            ],
        }