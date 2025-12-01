# Copyright 2025 The WheelOS Team. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Created Date: 2025-11-30
# Author: daohu527@gmail.com



ISSUES_LINK = "https://github.com/wheelos/apollo-lite"
SUPPORT_EMAIL = "support@wheelos.cn"

ASCII_WHEELOS = r"""
           __              __
 _      __/ /_  ___  ___  / /___  _____
| | /| / / __ \/ _ \/ _ \/ / __ \/ ___/
| |/ |/ / / / /  __/  __/ / /_/ (__  )
|__/|__/_/ /_/\___/\___/_/\____/____/
"""


def build_welcome_text() -> str:
    """
    Build the welcome banner text including ASCII art and contact info.
    """
    lines = [
        ASCII_WHEELOS,
        "",
        f"GitHub: {ISSUES_LINK}",
        f"Email : {SUPPORT_EMAIL}",
        "",
    ]
    return "\n".join(lines)


def show_welcome() -> None:
    """
    Display the welcome banner to the user.
    """
    banner = build_welcome_text()
    print(banner)
