from whl_deploy.utils.common import info
from whl_deploy.prepare.install_docker import DockerManager
from whl_deploy.prepare.install_nvidia_container_toolkit import NvidiaToolkitManager
from whl_deploy.host.config import config


class ContainerSetup:
    """Class to manage the setup of the host environment."""

    def __init__(self):
        self.mirror_region = config.mirror_region
        self.os_info = config.os_info
        self.docker_manager = DockerManager(
            mirror_region=self.mirror_region, os_info=self.os_info
        )
        self.nvidia_toolkit_manager = NvidiaToolkitManager(
            mirror_region=self.mirror_region, os_info=self.os_info
        )

    def setup_all(self, uninstall: bool = False):
        """Set up all components of the host environment."""
        info(
            f"--- 🚀 Starting Full Environment {'Uninstalling' if uninstall else 'Setting up'} ---"
        )
        self.setup_docker(uninstall)
        self.setup_nvidia_toolkit(uninstall)
        info("--- 🎉 Full Environment Setup Complete ---")

    def setup_docker(self, uninstall: bool = False):
        """Set up or uninstall Docker."""
        info("--- Step: Setting up Docker Environment ---")
        (self.docker_manager.uninstall if uninstall else self.docker_manager.install)()
        info("--- ✅ Docker Environment Setup Complete ---")

    def setup_nvidia_toolkit(self, uninstall: bool = False):
        """Set up or uninstall NVIDIA Container Toolkit."""
        info("--- Step: Setting up NVIDIA Toolkit ---")
        (
            self.nvidia_toolkit_manager.uninstall
            if uninstall
            else self.nvidia_toolkit_manager.install
        )()
        info("--- ✅ NVIDIA Toolkit Setup Complete ---")
