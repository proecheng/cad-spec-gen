"""BUILD phase command wrapper."""


def run(args):
    from cad_pipeline import cmd_build

    return cmd_build(args)
