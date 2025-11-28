## 🚀 Quick Start

`whl-deploy` simplifies Apollo deployment into two streamlined phases: **Packaging** (creating a portable release) and **Deploying** (setting up the host).

### 1. One-Step Deployment (Run/Install)

This is the standard scenario for end-users. Using a generated release bundle (e.g., `wheelos_1.0.0_ubuntu22.04_x86_64_nvidia.tar`), you can restore the entire environment—including source code, Docker images, and data—with a single command.

**The tool automates the following workflow:**
1.  📦 **Unpack**: Extracts the bundle to the workspace.
2.  📖 **Configure**: Loads the internal `manifest.yaml`.
3.  🚀 **Deploy**: Installs artifacts (Source, Docker, Maps, Models).
4.  ⚙️ **Post-Run**: Executes setup scripts (e.g., GPU checks).

```bash
# Standard installation from a release bundle
whl-deploy run --bundle wheelos_1.0.0_ubuntu22.04_x86_64_nvidia.tar

# Using aliases (Short syntax)
whl-deploy r -b wheelos_1.0.0_ubuntu22.04_x86_64_nvidia.tar
```

> **💡 Tip: Development Mode**
> If you are working in a development environment where the code is already present (git cloned) and you don't have a tarball, you can run deployment directly using the local manifest:
> ```bash
> whl-deploy run --manifest whl_deploy/manifest.yaml
> ```

---

### 2. Creating a Release (Pack)

For developers or CI/CD pipelines, `whl-deploy` consolidates all resources defined in your `manifest.yaml` into a single, distributable file.

**Key Features:**
*   **Auto-Naming**: Automatically generates names like `{project}_{ver}_{os}_{arch}_{gpu}.tar`.
*   **Smart Packing**: Fetches remote resources and standardizes directory structures.
*   **No-Double-Compression**: Uses uncompressed tar for the outer shell to speed up deployment.

```bash
# Pack using a specific manifest file
whl-deploy pack --manifest whl_deploy/manifest.yaml

# Using aliases
whl-deploy p -m whl_deploy/manifest.yaml
```

---

### 3. Configuration (Manifest)

`whl-deploy` adopts a "Configuration as Code" approach. The `manifest.yaml` defines **what** to pack (inputs) and **where** to deploy it (outputs).

📄 **View the Example Manifest:**
[👉 **whl_deploy/manifest.yaml**](https://github.com/wheelos-tools/whl-deploy/blob/main/whl_deploy/manifest.yaml)

---

### 4. Command Reference

#### Global Options
These flags apply to all commands:
*   `-m, --manifest <path>`: Specify a custom manifest file path (Default: `./manifest.yaml`).
*   `-v, --verbose`: Enable detailed debug logging.

#### Subcommands

| Command | Alias | Description | Key Flags |
| :--- | :--- | :--- | :--- |
| **`run`** | `r`, `install`, `i` | Deploy artifacts to the host system. | `-b, --bundle <path>`: Path to the `.tar` file to unpack. |
| **`pack`** | `p` | Create a consolidated release package. | N/A (Uses manifest settings) |

---

### 🤝 Contribution & Support

`whl-deploy` aims to standardize the complex deployment of autonomous driving software. If you have questions, suggestions, or wish to contribute:

*   🐛 **Report Bugs**: Submit an Issue.
*   🛠️ **Contribute**: Fork the repo and create a Pull Request.
