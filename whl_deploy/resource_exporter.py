from pathlib import Path

from whl_deploy.utils.common import info, warning, prompt_for_confirmation
from whl_deploy.resource.cache import (
    CacheManager,
    BAZEL_CACHE_DIR,
)
from whl_deploy.resource.docker_image import (
    DockerImageManager,
)
from whl_deploy.resource.maps import (
    MapManager,
    DEFAULT_MAP_IMPORT_DIR,
)
from whl_deploy.resource.models import (
    ModelManager,
    DEFAULT_MODEL_IMPORT_DIR,
)
from whl_deploy.resource.source_code import (
    SourcePackageManager,
    DEFAULT_SOURCE_DIR,
)


class ResourceExporter:
    """Class to handle the export of various resources."""

    PACKAGE_SUBDIRS = {
        "source_code": "source_code",
        "docker_image": "docker_image",
        "maps": "maps",
        "models": "models",
        "cache": "cache",
    }

    def export_all(
        self, output_package_path: str, non_interactive: bool = False
    ) -> None:
        """Export all resources into a single package."""
        temp_extract_dir = self._prepare_temp_directory(output_package_path)

        # Call individual export methods based on available resources
        # Assume we have a method for each resource similar to import
        for resource_key in self.PACKAGE_SUBDIRS:
            method_name = f"export_{resource_key}"
            if hasattr(self, method_name):
                getattr(self, method_name)(temp_extract_dir)

        info("--- 🎉 Full Data Export Complete ---")

    def _export_resource(self, resource_key: str, output_path: str, force_overwrite):
        method_name = f"export_{resource_key}"
        getattr(self, method_name)(output_path, force_overwrite=False)

    def _prepare_temp_directory(self, package_path: str) -> Path:
        package_path_obj = Path(package_path)
        temp_extract_dir = package_path_obj.parent / f"{package_path_obj.stem}_exported"
        temp_extract_dir.mkdir(parents=True, exist_ok=True)
        return temp_extract_dir

    # Resource export methods
    def export_source_code(self, output_dir: Path, force_overwrite=False):
        info(f"Exporting source code to '{output_dir}'...")
        source_package_manager = SourcePackageManager()
        source_package_manager.export_source_package(DEFAULT_SOURCE_DIR, output_dir)
        info("--- ✅ Source Code Export Complete ---")

    def export_docker_image(self, output_dir: Path, force_overwrite=False):
        info(f"Exporting Docker image to '{output_dir}'...")
        docker_image_manager = DockerImageManager()
        docker_image_manager.save_images(
            "docker_image_name", output_dir
        )  # Replace with actual image name
        info("--- ✅ Docker Image Export Complete ---")

    def export_maps(self, output_dir: Path, force_overwrite=False):
        info(f"Exporting maps to '{output_dir}'...")
        map_manager = MapManager()
        map_manager.export_map(DEFAULT_MAP_IMPORT_DIR, output_dir)
        info("--- ✅ Maps Export Complete ---")

    def export_models(self, output_dir: Path, force_overwrite=False):
        info(f"Exporting models to '{output_dir}'...")
        model_manager = ModelManager()
        model_manager.export_model(DEFAULT_MODEL_IMPORT_DIR, output_dir)
        info("--- ✅ Models Export Complete ---")

    def export_cache(self, output_dir: Path, force_overwrite=False):
        info(f"Exporting cache to '{output_dir}'...")
        cache_manager = CacheManager()
        cache_manager.export_cache(BAZEL_CACHE_DIR, output_dir)
        info("--- ✅ Cache Export Complete ---")
