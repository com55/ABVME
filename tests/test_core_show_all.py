import unittest
from types import SimpleNamespace

from UnityPy.enums import ClassIDType

from models.core_model import available_assets, filter_assets_by_available_types


def _asset(obj_type: ClassIDType) -> SimpleNamespace:
    return SimpleNamespace(obj_type=obj_type)


class FilterAssetsByAvailableTypesTests(unittest.TestCase):
    def test_show_all_returns_every_asset(self):
        assets = [
            _asset(ClassIDType.Texture2D),
            _asset(ClassIDType.Mesh),
            _asset(ClassIDType.TextAsset),
        ]

        result = filter_assets_by_available_types(assets, available_assets, show_all=True)

        self.assertEqual(result, assets)

    def test_default_filter_keeps_only_available_types(self):
        assets = [
            _asset(ClassIDType.Texture2D),
            _asset(ClassIDType.Mesh),
            _asset(ClassIDType.TextAsset),
            _asset(ClassIDType.Material),
        ]

        result = filter_assets_by_available_types(assets, available_assets, show_all=False)

        self.assertEqual(
            [asset.obj_type for asset in result],
            [ClassIDType.Texture2D, ClassIDType.TextAsset],
        )

    def test_filtered_result_is_a_copy(self):
        assets = [_asset(ClassIDType.Texture2D)]

        result = filter_assets_by_available_types(assets, available_assets, show_all=True)

        self.assertEqual(result, assets)
        self.assertIsNot(result, assets)


if __name__ == "__main__":
    unittest.main()
