# whl_deploy

`whl_deploy` is a powerful tool designed to significantly simplify the complex process of setting up and deploying Apollo. It automates host environment prerequisites and streamlines the import/export of essential Apollo resources, ensuring a highly efficient, consistent, and seamless deployment experience.

## ✨ Key Features

`whl_deploy` provides the following core functionalities, covering the entire Apollo deployment lifecycle:

1.  **Automated Host Environment Setup**:
    *   Automatically installs and configures Docker and the NVIDIA Container Toolkit.
    *   Applies necessary system-level optimizations and configurations to provide an optimal environment for Apollo.
2.  **Apollo Resource Import & Deployment**:
    *   One-command import and deployment of all critical Apollo components, including:
        *   Core Container Images (Docker Image)
        *   Apollo Source Code
        *   AI Models
        *   High-Definition Maps
        *   Compiled Cache files
    *   Drastically reduces Apollo's initial setup and startup time.
3.  **Resource Package Export & Distribution (Helper)**:
    *   Offers a convenient function to package pre-configured or downloaded Apollo resources (e.g., source code, models, cache) into reusable bundles.
    *   These resource packages are ideal for quick and consistent deployments across multiple machines (as input for Step 2), especially useful in offline environments or for large-scale deployments.

## 🚀 Quick Start

This section guides you on how to quickly install and use `whl_deploy`.

### 1. Installation

To support the latest PEP 660 (editable installs), ensure your `setuptools` and `pip` versions are up-to-date before installation:

```bash
# Highly Recommended: Upgrade setuptools and pip first
pip install setuptools -U
pip install --upgrade pip

# Install whl-deploy
pip install whl-deploy
```

### setup env
```shell
whl-deploy setup all
```

### import
```shell
whl-deploy import all --package=source
```

### export
```shell
whl-deploy export all --package=source
```

### 2. Configure Host Environment (Setup Host)

This is the foundation for running Apollo. You can choose a one-command full configuration or proceed step-by-step as needed.

#### Option 1: One-Command Full Configuration (Recommended)

This command will automatically install Docker, the NVIDIA Container Toolkit, and perform necessary system configurations.

```bash
whl-deploy setup full
```

#### Option 2: Step-by-Step Configuration

If you require more granular control, you can execute these commands individually:

```bash
# Only install and configure Docker
whl-deploy setup docker

# Only install and configure NVIDIA Container Toolkit
whl-deploy setup nvidia

# Only perform system-level host configurations (e.g., kernel parameters, user groups)
whl-deploy setup host
```

### 3. Import & Export Apollo Resources

`whl_deploy` provides flexible commands to manage various Apollo resources.

#### 3.1 Source Code

*   **Import Source Code Package**: Imports a zipped Apollo source code archive to a specified location.
    ```bash
    whl-deploy import source-code --input=apollo-lite-main.zip
    ```
    *   **Hint**: This command typically unzips the code into Apollo's specific working directory, either inside or outside the container.

*   **Export Source Code Package**: Packages the source code from the current Apollo environment for reuse elsewhere.
    ```bash
    whl-deploy export source-code --output=apollo-main.zip
    ```
    *   **Hint**: The exported package can be used as input for `import source-code`.

#### 3.2 Compiled Cache (Bazel Cache)

The Bazel compilation cache is crucial for accelerating the Apollo build process.

*   **Import Compiled Cache**: Imports a pre-packaged Bazel cache.
    ```bash
    whl-deploy import cache --input=bazel_cache.tar.gz
    ```

*   **Export Compiled Cache**: Exports the current Bazel cache for use across multiple machines or in future deployments.
    ```bash
    whl-deploy export cache --output=bazel_cache.tar.gz
    ```

#### 3.3 Docker Images

Manage Apollo's core container images.

*   **Import Docker Image**: Imports a Docker image from a `.tar` file. This is useful for offline deployments or pre-loading images.
    ```bash
    whl-deploy import docker-image --input=whl_docker_image.tar
    ```

*   **Export Docker Image**:
    *   **Export information about all currently recognized Apollo-related Docker images**:
        ```bash
        whl-deploy export docker-image --info
        ```
        *   **Hint**: This command lists the names and tags of all Apollo-related images managed or recognized by `whl_deploy`.

    *   **Export a specific Docker image to a `.tar` file**:
        ```bash
        whl-deploy export docker-image --input=nvidia/cuda:11.8.0-cudnn8-devel-ubuntu20.04 --output=cuda_image.tar
        ```
        *   **Note**: Here, the `--input` parameter should specify the **name and tag of the image to be exported**, not a file. I have corrected this based on the actual functionality. If you wish to export a specific Apollo base image, replace it with the corresponding name. For example: `whl-deploy export docker-image --input=apollo:dev-latest --output=apollo_dev.tar`

#### 3.4 High-Definition Maps (HD Maps)

*   **Import HD Maps** (TODO - To Be Implemented)

*   **Export HD Maps** (TODO - To Be Implemented)

#### 3.5 AI Models

*   **Import AI Models** (TODO - To Be Implemented)

*   **Export AI Models** (TODO - To Be Implemented)

## 🤝 Contribution & Support

`whl_deploy` aims to simplify Apollo deployment. If you have any questions, suggestions, or wish to contribute code, feel free to submit an Issue or a Pull Request.
