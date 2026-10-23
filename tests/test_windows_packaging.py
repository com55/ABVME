import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "packaging" / "windows" / "ABVME.iss"
WORKFLOW = ROOT / ".github" / "workflows" / "build_release.yml"


class WindowsInstallerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = INSTALLER.read_text(encoding="utf-8")

    def test_upgrade_does_not_run_the_previous_uninstaller(self) -> None:
        self.assertNotIn("GetUninstallString", self.script)
        self.assertNotIn("Exec(UnInstStr", self.script)

    def test_registration_does_not_claim_the_user_default(self) -> None:
        self.assertNotIn('Subkey: "Software\\Classes\\.bundle"; ValueType:', self.script)
        self.assertNotIn('Subkey: "Software\\Classes\\.unity3d"; ValueType:', self.script)
        self.assertNotIn("Explorer\\FileExts", self.script)

    def test_upgrade_removes_only_abvmes_legacy_extension_defaults(self) -> None:
        self.assertIn("RemoveLegacyExtensionDefault('.bundle'", self.script)
        self.assertIn("RemoveLegacyExtensionDefault('.unity3d'", self.script)
        self.assertIn("(CurrentProgId = ProgId)", self.script)

    def test_open_with_registration_is_not_gated_by_an_upgrade_task(self) -> None:
        registry = self.script.split("[Registry]", 1)[1].split("[Run]", 1)[0]
        self.assertNotIn("Tasks: associate", registry)

    def test_registers_a_named_application_and_capabilities(self) -> None:
        self.assertIn("Software\\Classes\\Applications\\{#MyAppExeName}", self.script)
        self.assertIn("FriendlyAppName", self.script)
        self.assertIn("Software\\RegisteredApplications", self.script)
        self.assertIn("Capabilities\\FileAssociations", self.script)


class WindowsExecutableMetadataTests(unittest.TestCase):
    def test_nuitka_build_embeds_product_identity(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("file-description: ABVME", workflow)
        self.assertIn("product-name: ABVME", workflow)
        self.assertIn("file-version:", workflow)
        self.assertIn("product-version:", workflow)


if __name__ == "__main__":
    unittest.main()
