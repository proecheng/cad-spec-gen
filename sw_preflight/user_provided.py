"""用户手动提供 STEP 文件流程 — prompt 主入口 + 三选一 (Task 22)"""
from sw_preflight.types import UserChoiceResult
from sw_preflight import io


def _bom_key(row: dict) -> str:
    """BOM 行唯一标识 — 用 name_cn + part_no 组合"""
    return f"{row.get('name_cn','')}|{row.get('part_no','')}"


def prompt_user_provided(missing_rows: list[dict], copy_files: bool = True) -> UserChoiceResult:
    """三选一主入口：stand_in / skip / provide（provide 走 file dialog 循环）"""
    if not missing_rows:
        return UserChoiceResult(provided_files={}, stand_in_keys=set(), skipped_keys=set())
    choice = io.three_choice_prompt(missing_count=len(missing_rows))
    if choice == 'stand_in':
        return UserChoiceResult(provided_files={},
                                stand_in_keys={_bom_key(r) for r in missing_rows},
                                skipped_keys=set())
    if choice == 'skip':
        return UserChoiceResult(provided_files={}, stand_in_keys=set(),
                                skipped_keys={_bom_key(r) for r in missing_rows})
    # choice == 'provide' → 逐行 file dialog
    provided, stand_in, skipped = {}, set(), set()
    for i, row in enumerate(missing_rows, 1):
        title = f"为 {row.get('name_cn','?')} 选择 STEP ({i}/{len(missing_rows)})"
        path = io.ask_step_file(title)
        if path is None:
            sub = input(f"取消了 — 该行用 [1] stand-in / [2] 跳过: ").strip()
            if sub == '2':
                skipped.add(_bom_key(row))
            else:
                stand_in.add(_bom_key(row))
            continue
        # 校验 + 复制（复制逻辑在 Task 23）
        if copy_files:
            from sw_preflight.user_provided import copy_to_user_provided  # forward ref
            dest = copy_to_user_provided(path, row)
            provided[_bom_key(row)] = dest
        else:
            provided[_bom_key(row)] = path
    return UserChoiceResult(provided_files=provided, stand_in_keys=stand_in,
                            skipped_keys=skipped)
