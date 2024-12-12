{
  description = "rmacs-pkg";

  outputs = _: {
    # Expose rmacsModules for use in parent projects
    rmacsModules = {
      channel-switch = import ./packages/channel-switch;
    };
  };
}
