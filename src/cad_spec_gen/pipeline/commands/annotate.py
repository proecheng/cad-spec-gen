"""ANNOTATE phase command wrapper."""


def run(args):
    from cad_pipeline import cmd_annotate

    return cmd_annotate(args)
