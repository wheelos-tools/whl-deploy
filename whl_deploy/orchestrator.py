from whl_deploy.utils.common import info, warning
from whl_deploy.resource_exporter import ResourceExporter
from whl_deploy.resource_importer import ResourceImporter
from whl_deploy.container_setup import ContainerSetup


class OrchestratorError(Exception):
    """Custom exception for errors during orchestration processes."""

    pass


class HostSetupOrchestrator:
    """Orchestrates the setup of the host environment and the import/export of data."""

    def __init__(self):
        self.host_setup = ContainerSetup()
        self.resource_importer = ResourceImporter()
        self.resource_exporter = ResourceExporter()

    def setup_all(self, uninstall: bool = False) -> None:
        self.host_setup.setup_all(uninstall)

    def import_all(self, package_path: str, non_interactive: bool = False) -> None:
        self.resource_importer.import_all(package_path, non_interactive)

    def export_all(self, output_package_path: str) -> None:
        self.resource_exporter.export_all(output_package_path)
