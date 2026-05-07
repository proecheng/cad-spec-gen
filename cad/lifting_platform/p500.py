# ENRICHED_PLACEHOLDER — geometry approximated, not dimensionally accurate
# tpl_type=unknown envelope=(40.0,40.0,20.0)
import cadquery as cq

def make_p500():
    # 此件由 L3 富化 Envelope 生成，精度有限
    # 生成的 .py 与 .step 必须保持同目录同名
    return cq.importers.importStep(str(__import__('pathlib').Path(__file__).with_suffix('.step')))


# Backward-compatible alias for older direct callers
p500 = make_p500
