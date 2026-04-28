"""CODEGEN phase command wrapper."""


def run(args):
    from cad_pipeline import cmd_codegen

    return cmd_codegen(args)
