"""RENDER phase command wrapper."""


def run(args):
    from cad_pipeline import cmd_render

    return cmd_render(args)
