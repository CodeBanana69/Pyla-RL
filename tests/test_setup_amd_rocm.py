import unittest

from setup_amd_rocm import (
    pci_dev_ids_from_pnp,
    rdna3_match_from_dev_ids,
    rdna3_match_from_gpu_name,
)


class SetupAmdRocmTests(unittest.TestCase):
    def test_pci_dev_ids_from_pnp_extracts_upper_hex(self):
        pnp = r"PCI\VEN_1002&DEV_744C&SUBSYS_C7501DA2&REV_CF"
        self.assertEqual(pci_dev_ids_from_pnp(pnp), ["744C"])

    def test_pci_dev_ids_multiple_dev_tokens(self):
        # Synthetic string with two DEV occurrences (unusual but parser should collect both).
        pnp = r"X\DEV_747e&FOO\DEV_7480"
        ids = pci_dev_ids_from_pnp(pnp)
        self.assertEqual(ids, ["747E", "7480"])

    def test_rdna3_match_from_dev_ids(self):
        self.assertTrue(rdna3_match_from_dev_ids(["744c"]))
        self.assertFalse(rdna3_match_from_dev_ids(["73BF"]))  # RDNA2 example id

    def test_rdna3_match_from_gpu_name_positive(self):
        self.assertTrue(rdna3_match_from_gpu_name("AMD Radeon RX 7900 XT"))

    def test_rdna3_match_from_gpu_name_blocks_common_rdna2(self):
        self.assertFalse(rdna3_match_from_gpu_name("AMD Radeon RX 6700 XT"))

    def test_rdna3_match_from_gpu_name_non_amd(self):
        self.assertFalse(rdna3_match_from_gpu_name("NVIDIA GeForce RTX 4090"))


if __name__ == "__main__":
    unittest.main()
