{ config, pkgs, lib, ... }: with lib; let
  pyproject = lib.importTOML (config.mkDerivation.src + /pyproject.toml);
  pkgsCross = import <nixpkgs> { system = config.system; };
in {
  config = {
    # Systemd service definition
    systemd.services.channel-switch = {
      description = "Resilient Mesh Automatic Channel Selection";
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Environment = "PATH=/run/current-system/sw/bin:/run/wrappers/bin:/bin:/usr/bin";
        ExecStart = "/run/current-system/sw/bin/channel-switch";
        Restart = "no"; #"on-failure";
        RestartSec = "5s";
      };
      serviceConfig.User = "root";
      after = [
        "mdmagent.service"
      ];  # Ensure these services start first
      wants = [
        "mdmagent.service"
      ]; 
    };

    # Ensure the required packages are installed
    environment.systemPackages = [
      pkgs.python3
      pkgs.wpa_supplicant
      (pkgs.python3Packages.buildPythonApplication {
        pname = "channel-switch";
        version = "1.0.0";
        src = ./.;

        build-system = with pkgs.python3Packages; [
          setuptools
        ];

        propagatedBuildInputs = [
          pkgs.python3Packages.pyyaml
          pkgs.python3Packages.systemd
          pkgs.python3Packages.msgpack
        ];

        meta = with lib; {
          description = "Resilient Mesh Automatic Channel Selection";
          license = licenses.asl20;
          maintainers = [
            {
              name = "Roopa Shanmugam";
              email = "roopa.shanmugam@tii.ae";
            }
          ];
        };
      })
    ];

    # Additional imports and pip configuration
    imports = [
      dream2nix.modules.dream2nix.pip
    ];

    deps = { nixpkgs, ... }: {
      python = nixpkgs.python3;
    };

    inherit (pyproject.project) name version;
    

    buildPythonPackage = {
      pyproject = lib.mkForce true;
      #build-system = [ config.deps.python.pkgs.setuptools ];
      pythonImportsCheck = [
        "mdmagent"
      ];
    };

    pip = {
      editables.${pyproject.project.name} = "./mdmagent";
      requirementsList = pyproject.project.dependencies or [ ];
      requirementsFiles = pyproject.tool.setuptools.dynamic.dependencies.file or [ ];
      flattenDependencies = true;
      pipFlags = [ "--no-deps" ];
      nativeBuildInputs = [ config.deps.gcc ];
    };
  };
}
