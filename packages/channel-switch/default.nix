{ config, pkgs, lib, ... }: with lib; {
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
  };
}
let
  pyproject = lib.importTOML (config.mkDerivation.src + /pyproject.toml);
  pkgsCross = import <nixpkgs> { system = config.system; };

in
{
  imports = [
    dream2nix.modules.dream2nix.pip
  ];

  deps =
    { nixpkgs, ... }:
    {
      python = nixpkgs.python3;
      inherit (nixpkgs)
        batctl
        openssl
        iw
        kmod
        ebtables
        libfaketime
        gcc
        swig
        bash
        killall
        coreutils
        iproute2
        gnugrep
        gnused
        gawk
        customWpaSupplicant
        hostapd
        radvd
        ;
    };

  inherit (pyproject.project) name version;

  mkDerivation = {
    src = lib.cleanSourceWith {
      src = lib.cleanSource ./.;
      filter =
        name: type:
          !(builtins.any (x: x) [
            (lib.hasSuffix ".nix" name)
            (lib.hasPrefix "." (builtins.baseNameOf name))
            (lib.hasSuffix "flake.lock" name)
          ]);
    };
    buildInputs = [ config.deps.bash ];
    propagatedBuildInputs = [ config.deps.batctl ];
    postFixup =
      let
        binPath = lib.makeBinPath (
          with config.deps;
          [
            ebtables
            openssl
            libfaketime
            batctl
            killall
            iw
            iproute2
            kmod
            coreutils
            gnugrep
            gawk
            gnused
          ]
        );
      in
      ''
        ${builtins.foldl' (s: p: s + "wrapProgram $out/bin/${p} --set PATH ${binPath};") "" [
          "config_converter_mesh.sh"
        ]}
      '';
  };

  buildPythonPackage = {
    pyproject = lib.mkForce true;
    build-system = [ config.deps.python.pkgs.setuptools ];
    pythonImportsCheck = [
      "channel-switch"
    ];
  };

  pip = {
    editables.${pyproject.project.name} = "./channel-switch";
    requirementsList = pyproject.project.dependencies or [ ];
    requirementsFiles = pyproject.tool.setuptools.dynamic.dependencies.file or [ ];
    flattenDependencies = true;
    pipFlags = [ "--no-deps" ];
    nativeBuildInputs = [ config.deps.gcc ];
  };
}