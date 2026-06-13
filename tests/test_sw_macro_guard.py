"""Tests for sw_macro_guard — VBA macro extraction + validation (API verified)."""
from sw_2026_skill.sw_macro_guard import extract_vba_code, validate_vba_macro


class TestExtractVbaCode:
    def test_extract_fenced_block(self):
        code = extract_vba_code("```vba\nSub main()\nEnd Sub\n```")
        assert "Sub main()" in code
        assert "```" not in code

    def test_no_fence_passthrough(self):
        assert "Sub main" in extract_vba_code("Sub main()\nEnd Sub")

    def test_empty(self):
        assert extract_vba_code("") == ""


class TestValidateVbaMacro:
    def test_valid_minimal(self):
        code = """Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2
Sub main()
    Set swApp = Application.SldWorks
End Sub"""
        result = validate_vba_macro(code)
        assert result.ok
        assert len(result.issues) == 0

    def test_missing_sldworks_object(self):
        code = """Sub main()
    MsgBox "hello"
End Sub"""
        result = validate_vba_macro(code)
        assert not result.ok
        assert any("SldWorks" in i for i in result.issues)

    def test_missing_end_sub(self):
        code = """Dim swApp As SldWorks.SldWorks
Sub main()
    MsgBox "hello"
"""
        result = validate_vba_macro(code)
        assert not result.ok
        assert any("End Sub" in i for i in result.issues)

    def test_todo_detected(self):
        code = """Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2
Sub main()
    ' TODO: implement later
End Sub"""
        result = validate_vba_macro(code)
        assert not result.ok
        assert any("占位符" in i or "未完成" in i for i in result.issues)

    def test_empty_code(self):
        result = validate_vba_macro("")
        assert not result.ok
        assert any("空" in i for i in result.issues)
