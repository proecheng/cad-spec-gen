"""PHOTO3D contract gate command wrapper."""


def run(args):
    from cad_pipeline import cmd_photo3d

    return cmd_photo3d(args)
