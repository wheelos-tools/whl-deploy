import tarfile
import shutil
from pathlib import Path
from whl_deploy.utils.common import info, warning, prompt_for_confirmation


from whl_deploy.resource.cache import (
    CacheManager,
    DEFAULT_CACHE_EXPORT_FILENAME,
    BAZEL_CACHE_DIR,
)
from whl_deploy.resource.docker_image import (
    DockerImageManager,
    DEFAULT_IMAGE_EXPORT_FILENAME,
)
from whl_deploy.resource.maps import (
    MapManager,
    MAP_IMPORT_DIR,
    DEFAULT_MAP_EXPORT_FILENAME,
)
from whl_deploy.resource.models import (
    ModelManager,
    MODEL_IMPORT_DIR,
    DEFAULT_MODEL_EXPORT_FILENAME,
)
from whl_deploy.resource.source_code import (
    SourcePackageManager,
    DEFAULT_SOURCE_DIR,
    DEFAULT_SOURCE_EXPORT_FILENAME,
)


class ResourceImporter:
    """Class to handle the import of various resources."""

    PACKAGE_SUBDIRS = {
        "source_code": "source_code",
        "docker_image": "docker_image",
        "maps": "maps",
        "models": "models",
        "cache": "cache",
    }

    def import_all(self, package_path: str, non_interactive: bool = False) -> None:
        """Import all resources from a given package."""
        temp_extract_dir = self._prepare_temp_directory(package_path)
        self._extract_package(package_path, temp_extract_dir)

        for resource_key in self.PACKAGE_SUBDIRS:
            if prompt_for_confirmation(
                f"Import {resource_key.replace('_', ' ')}", non_interactive
            ):
                self._import_resource(resource_key, temp_extract_dir)

        shutil.rmtree(temp_extract_dir)
        info("--- 🎉 Full Data Import Complete ---")

    def _prepare_temp_directory(self, package_path: str) -> Path:
        package_path_obj = Path(package_path)
        temp_extract_dir = (
            package_path_obj.parent / f"{package_path_obj.stem}_extracted"
        )
        temp_extract_dir.mkdir(parents=True, exist_ok=True)
        return temp_extract_dir

    def _extract_package(self, package_path: str, temp_extract_dir: Path):
        info(f"Extracting package '{package_path}' to '{temp_extract_dir}'...")
        with tarfile.open(package_path, "r") as tar:
            tar.extractall(path=temp_extract_dir)
        info("Package extracted successfully.")

    def _import_resource(self, resource_key: str, input_path: str, force_overwrite):
        method_name = f"import_{resource_key}"
        getattr(self, method_name)(input_path, force_overwrite=False)

    def get_default_filename(self, resource_key) -> str:
        """Return default filename for each resource key."""
        default_filenames = {
            "source_code": DEFAULT_SOURCE_EXPORT_FILENAME,
            "docker_image": DEFAULT_IMAGE_EXPORT_FILENAME,
            "maps": DEFAULT_MAP_EXPORT_FILENAME,
            "models": DEFAULT_MODEL_EXPORT_FILENAME,
            "cache": DEFAULT_CACHE_EXPORT_FILENAME,
        }
        return default_filenames.get(resource_key, "")

    # Resource import methods
    def import_source_code(self, input_path: str, force_overwrite: bool = False):
        info(f"Importing source code from '{input_path}'...")
        source_package_manager = SourcePackageManager()
        source_package_manager.import_source_package(
            input_path, DEFAULT_SOURCE_DIR, force_overwrite
        )
        info("--- ✅ Source Code Import Complete ---")

    def import_docker_image(self, input_path: str, force_overwrite: bool = False):
        info(f"Importing Docker image from '{input_path}'...")
        docker_image_manager = DockerImageManager()
        docker_image_manager.load_images(input_path)
        info("--- ✅ Docker Image Import Complete ---")

    def import_maps(self, input_path: str, force_overwrite: bool = False):
        info(f"Importing maps from '{input_path}'...")
        map_manager = MapManager()
        map_manager.import_map(input_path, MAP_IMPORT_DIR)
        info("--- ✅ Maps Import Complete ---")

    def import_models(self, input_path: str, force_overwrite: bool = False):
        info(f"Importing models from '{input_path}'...")
        model_manager = ModelManager()
        model_manager.import_model(input_path, MODEL_IMPORT_DIR)
        info("--- ✅ Models Import Complete ---")

    def import_cache(self, input_path: str, force_overwrite: bool = False):
        info(f"Importing cache from '{input_path}'...")
        cache_manager = CacheManager()
        cache_manager.import_cache(input_path, BAZEL_CACHE_DIR)
        info("--- ✅ Cache Import Complete ---")
