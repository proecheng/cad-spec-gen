"""SPEC phase command wrapper."""


def run(args):
    from cad_pipeline import cmd_spec

    return cmd_spec(args)
