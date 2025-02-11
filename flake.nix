{
  description = "HyperAlloc Benchmark Environemnt";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
  };

  outputs = { self, nixpkgs, ... }: let
    supportedSystems = [ "aarch64-linux" "x86_64-linux"
                         "aarch64-darwin" "x86_64-darwin" ];
    forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
  in {
    devShells = forAllSystems (system: let pkgs = nixpkgs.legacyPackages.${system}; in {
      default = pkgs.mkShellNoCC {
        buildInputs = with pkgs; [
          python312
        ] ++ (with pkgs.python312Packages; [
            numpy
            seaborn
            pandas
            psutil
            qemu
            ipykernel
            scipy
        ]);
      };
    });
  };
}
