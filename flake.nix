{
  description = "rotki project with uv-managed virtualenv";

  inputs = {
    nixpkgs.url          = "github:NixOS/nixpkgs/nixos-24.05";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url      = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        python311         = pkgs.python311;
        nodejsWithPython  = pkgs.nodejs.override { python3 = python311; };
        nodePackages      = pkgs.nodePackages.override { nodejs = nodejsWithPython; };
        pnpmWithPython311 = nodePackages.pnpm;

        devShell = pkgs.mkShell {
          name = "rotki-dev";
          buildInputs = [
            pkgs.gcc
            pkgs.stdenv.cc.cc.lib
            pkgs.bash
            pkgs.git
            pkgs.lzma
            pnpmWithPython311
            python311
            pkgs.uv
          ];

          shellHook = ''
            uv sync
            cd frontend
            pnpm install
            cd ..
          '';
        };
      in { inherit devShell; });
}
