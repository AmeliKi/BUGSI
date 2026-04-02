# IDS uEye EVS Plugin for OpenEB

This README provides instructions on building a plugin to operate IDS
uEye EVS cameras using the PROPHESEE Metavision SDK.

## Prerequisites

Before proceeding, ensure you have the freely available
[OpenEB](https://github.com/prophesee-ai/openeb) repository checked out
locally.

Along with this README, you should have received a patch file named:
`ueye_evs_plugin_openeb_5.0.0.patch`

Applying this patch to the OpenEB repository will integrate the
necessary changes to build the IDS uEye EVS plugin. The modifications
in this patch align with the recommended changes outlined in the
[official documentation](https://docs.prophesee.ai/5.0.0/architecture/camera_plugins/cx3_based_camera_plugin.html).

**Important:**
The patch version (e.g., `5.0.0`) must match the version of OpenEB you
have checked out.

---

## Build Instructions

### 1. Apply the Patch

Navigate to the OpenEB repository and apply the patch using:

```sh
git apply ueye_evs_plugin_openeb_5.0.0.patch
```

**Note:**
If whitespace issues prevent the patch from applying, try:

```sh
git apply --ignore-space-change ueye_evs_plugin_openeb_5.0.0.patch
```

### 2. Configure and Build

The patch adds a new build target: `ueye_evs_hal_plugin`

Configure the OpenEB CMake project as usual and build the new target:

```sh
cmake --build <build-folder> --target ueye_evs_hal_plugin
```

### 3. Locate the Compiled Library

After a successful build, the dynamic library will be placed in the same
directory as the main `hal_plugin_prophesee` target.

## Installation

After building the plugin, you must add the directory path of the
compiled plugin to the `MV_HAL_PLUGIN_PATH` environment variable. This
ensures that the Metavision SDK can detect and use the IDS uEye EVS plugin.

### Windows

On Windows, you need to install the driver using `wdi-simple.exe`. You
can obtain this tool from PROPHESEE by visiting the
[Windows installation page](https://docs.prophesee.ai/5.0.0/installation/windows.html#chapter-installation-windows-camera-plugin).

Once downloaded, install the driver for IDS' vendor and product IDs using the following command:

```sh
wdi-simple.exe -n "uEye EVS Device" -m "IDS Imaging Development Systems GmbH" -v 0x1409 -p 0x8e00
```

### Linux

To access the uEye EVS device **without using `sudo`**, you need to
install a `udev` rules file that configures the device’s permissions
appropriately.

The `udev` rule provided in the next steps will assign uEye EVS devices
to the group `ueye-evs-users`. This group is normally created by the
Debian package, but you'll need to create it manually:

```bash
sudo addgroup --system ueye-evs-users
```

To allow your user account to access the device without elevated
privileges, add yourself to the `ueye-evs-users` group:

```bash
sudo usermod -a -G ueye-evs-users "${SUDO_USER:-$(logname)}"
```

> Note: You must **log out and log back in** (or reboot) for the group change to take effect.

Next, install the provided udev rules file and apply the changes:

```bash
sudo cp ueye_evs_plugin_openeb_5.0.0_udev.rules /etc/udev/rules.d/99-ueye_evs.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```
