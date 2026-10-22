{ inputs, ... }:
{
  imports = [ inputs.flake-parts.flakeModules.modules ];
  systems = import inputs.systems;

  perSystem =
    { system, pkgs, ... }:
    {
      _module.args.pkgs = import inputs.nixpkgs {
        inherit system;
        config.allowUnfreePredicate =
          package:
          builtins.elem (inputs.nixpkgs.lib.getName package) [
            "titbit"
            "titbit-tools"
            "titbit-data"
            "titbit-web-probe"
            "titbit-web-objects"
          ];
      };
      formatter = pkgs.nixfmt;
    };
}
