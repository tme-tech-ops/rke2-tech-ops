# Spec 
Refactoring this blueprint from object-tech-ops to rke2-tech-ops

# Goal
- Refactory this repository's tech-ops directory and rke2-tech-ops.yaml
- Currently, this repo is fully functtioning for deploying seaweedfs and a monitoring stack that leverages the install-seaweedfs script, downloaded from github.
- I need to refactor this to swap out all install-seaweedfs logic and capabilities to the rke2_installer.sh logic and capabilities

# Helper reference files
- Within the scratch you will find the install-seaweedds and rke2_installer.sh scripts which will help understand the current functionality and variables (install-seaweefs) and teh target functionality and variables (rke2_installer.sh).
- Within in the scratch/fabric directory you will find the tasks.py file, which is the logic and functionality of the fabric plugin, which is the main plugin leveraged by this repository.

# Main feature instructions
- Ensure the new rke2 logic includes all command options of the rke2_installer.sh, this includes: install, install velero, install monitoring, uninstall, save, push, and join. It should also include optional logic for -registry and -tls-san. Also, the join modes should support both agent and server.
- Make sure the save mode is capable of pushing the arigapped archive to a targeted http server like the existing logic
- Make sure "airgapped mode" for installing is able to pull an archive from a defined http source
- Make sure to include all exportable variables in inputs.yaml and input_groups.
- Make sure to update the env_precheck.sh and env_postcheck.sh appropriately

# Addtional notes
- Make sure to read all the existing logic in the tech-ops and rke2_tech-ops.yaml to understand the blueprint's current functionality before making decisions
- Make sure to read the install-seaweedfs script to understand the current capabilities.
- Make sure to read the rke2-installer.sh script to understand the target capabilities.
- I've already updated the entrypoint file name to rke2_tech_ops.yaml
- I've already updated the script_url input with the correct github link
