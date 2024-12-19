{ config
, lib
, dream2nix
, ...
}:
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