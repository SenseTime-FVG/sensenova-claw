"""解析 JUnit XML → feature_matrix.md"""
import xml.etree.ElementTree as ET
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def main():
    RESULTS.mkdir(exist_ok=True)
    all_r = {}
    for f in RESULTS.glob("*.xml"):
        tree = ET.parse(f)
        for tc in tree.iter("testcase"):
            name = f"{tc.get('classname', '')}.{tc.get('name', '')}"
            if tc.find("failure") is not None:
                status = "FAIL"
            elif tc.find("skipped") is not None:
                status = "SKIP"
            else:
                status = "PASS"
            all_r.setdefault(f.stem, {})[name] = status

    total = sum(len(v) for v in all_r.values())
    passed = sum(1 for r in all_r.values() for s in r.values() if s == "PASS")
    failed = sum(1 for r in all_r.values() for s in r.values() if s == "FAIL")
    skipped = total - passed - failed
    lines = [f"# 功能验证矩阵\n\n总计: {total} | 通过: {passed} | 失败: {failed} | 跳过: {skipped}\n"]

    for suite, tests in sorted(all_r.items()):
        lines += [f"## {suite}\n", "| 用例 | 状态 |", "|------|------|"]
        for n, s in sorted(tests.items()):
            icon = "PASS" if s == "PASS" else "FAIL" if s == "FAIL" else "SKIP"
            lines.append(f"| {n} | {icon} |")
        lines.append("")

    output = RESULTS / "feature_matrix.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Feature matrix generated: {output}")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}")


if __name__ == "__main__":
    main()
