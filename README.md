RMACS(Resilient Mesh Automatic Channel Selection)v1.0 empowers the mesh network to autonomously switch to optimal channel by leveraging Clear Channel Assessment (CCA) and spectral scan data across specified frequency bands (2.4 GHz, and 5 GHz), thereby bolstering performance and resilience for sustained and reliable communication capabilities.

Project Structure

rmacs/

├── flake.nix                         # Main Nix flake definition for RMACS

└── packages/

    └── channel-switch/       # Module for channel-switch
    
        ├── default.nix               # Nix expression defining the module
        
        └── src/                      # Source code for the module

channel-switch:

The channel-switch module enables the mesh network to autonomously switch to the optimal channel by continuously monitoring traffic, detecting errors, and performing channel scans.