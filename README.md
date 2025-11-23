# whl_deploy

`whl_deploy` is a powerful tool **designed specifically for Apollo deployment**, aiming to significantly simplify the setup of Apollo environments and the import/export of resources. By automating key steps, `whl_deploy` ensures an efficient, consistent, and seamless Apollo deployment experience.

## ✨ Key Features

`whl_deploy` provides three core functionalities, covering the essential aspects of the Apollo deployment lifecycle:

1.  **Automated Environment Setup**: Installs and configures Docker, NVIDIA Container Toolkit, and optimizes the system, providing an ideal environment for Apollo.
2.  **Apollo Resource Import**: Unified import of core Apollo components, including Docker images, source code, AI models, high-definition maps, and compiled caches, drastically reducing initial setup and startup times.
3.  **Resource Packaging & Distribution**: Packages pre-configured or downloaded Apollo resources into reusable bundles, facilitating rapid deployment across multiple machines, especially useful in offline environments.

## 🚀 Quick Start

This section guides you on how to quickly install and use `whl_deploy`, focusing on the most common end-to-end deployment flow.

### 1. Installation

To ensure compatibility, please upgrade your `setuptools` and `pip` first:

```bash
# Highly Recommended: Upgrade setuptools and pip first
pip install setuptools -U
pip install --upgrade pip

# Install whl-deploy
pip install whl-deploy
```

### 2. End-to-End Deployment - Express Mode!

The following two commands are the essence of `whl_deploy`, covering the vast majority of Apollo deployment scenarios:

#### Step A: Prepare Host Environment

This command will automatically install Docker, the NVIDIA Container Toolkit, and perform necessary system configurations. This is the foundation for running Apollo.

```bash
whl-deploy setup all
```

#### Step B: Import Apollo Resources

After setting up the environment, you can import all pre-packaged core Apollo resources, such as source code, Docker images, AI models, etc., with a single command. **Please ensure your `source` package is ready.**

```bash
whl-deploy import all --package=source
```

---

### 3. More Granular Control

If you require more fine-grained control, `whl_deploy` also provides individual commands.

#### 3.1. Host Environment Configuration - Step-by-Step

In some cases, you might want to configure the host environment step-by-step:

```bash
# Only install and configure Docker
whl-deploy setup docker

# Only install and configure NVIDIA Container Toolkit
whl-deploy setup nvidia_toolkit
```

#### 3.2. Resource Import & Export - Category Management

`whl_deploy` allows you to manage various Apollo resources separately.

**a. Source Code**

*   **Import Source Code Package**: Imports a zipped Apollo source code archive to a specified location.
    ```bash
    whl-deploy import source_code --input=apollo-lite-main.zip
    ```
*   **Export Source Code Package**: Packages the source code from the current Apollo environment for reuse elsewhere.
    ```bash
    whl-deploy export source_code --output=apollo-main.zip
    ```

**b. Compiled Cache (Bazel Cache)**

The Bazel compilation cache is crucial for accelerating the Apollo build process.

*   **Import Compiled Cache**: Imports a pre-packaged Bazel cache.
    ```bash
    whl-deploy import cache --input=bazel_cache.tar.gz
    ```
*   **Export Compiled Cache**: Exports the current Bazel cache for use across multiple machines or in future deployments.
    ```bash
    whl-deploy export cache --output=bazel_cache.tar.gz
    ```

**c. Docker Images**

Manage Apollo's core container images.

*   **Import Docker Image**: Imports a Docker image from a `.tar` file. This is useful for offline deployments or pre-loading images.
    ```bash
    whl-deploy import docker_image --input=whl_docker_image.tar
    ```
*   **Export Docker Image**:
    *   **Export information about all currently recognized Apollo-related Docker images**:
        ```bash
        whl-deploy export docker_image --info
        ```
    *   **Export a specific Docker image to a `.tar` file**:
        ```bash
        whl-deploy export docker_image --input=nvidia/cuda:11.8.0-cudnn8-devel-ubuntu20.04 --output=cuda_image.tar
        ```
        *   **Note**: Here, the `--input` parameter should specify the **name and tag of the image to be exported**. For example, to export an Apollo development image, use: `whl-deploy export docker_image --input=apollo:dev-latest --output=apollo_dev.tar`

**d. High-Definition Maps (HD Maps) (TODO - To Be Implemented)**

*
```
# all maps
whl-deploy import maps -i="map_data.tar.gz"

# san_mateo only
whl-deploy import maps -i="your_map_dir/maps/san_mateo.tar.gz"
```
*   `whl-deploy export hd_maps --output=...`

**e. AI Models (TODO - To Be Implemented)**

*   `whl-deploy import models --input=...`
*   `whl-deploy export models --output=...`

## 🤝 Contribution & Support

`whl_deploy` aims to simplify Apollo deployment. If you have any questions, suggestions, or wish to contribute code, feel free to submit an Issue or a Pull Request.
