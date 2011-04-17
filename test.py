#!/usr/bin/env python
# Some tests for pingexp.

import unittest

import pingexp


class TestLostSequenceNumbers(unittest.TestCase):
    def setUp(self):
        pass


    def test_1(self):
        """Test no lost packets."""
        results = {'responses': [(1, 64, 0), (2, 64, 0), (3, 64, 0), (4, 64, 0)],
                    'summary': {'transmitted': 4, 'received': 4},
                    }

        r = pingexp.find_lost_sequence_numbers(results)

        self.assertTrue(r == [])


    def test_2(self):
        """Test first packet being lost."""
        results = {'responses': [(2, 64, 0), (3, 64, 0)],
                    'summary': {'transmitted': 3, 'received': 2},
                    }

        r = pingexp.find_lost_sequence_numbers(results)

        self.assertTrue(r == [1])


    def test_3(self):
        """Test first three packets being lost."""
        results = {'responses': [(4, 64, 0), (5, 64, 0), (6, 64, 0)],
                    'summary': {'transmitted': 6, 'received': 3},
                    }

        r = pingexp.find_lost_sequence_numbers(results)

        self.assertTrue(r == [1,2,3])


    def test_4(self):
        """Test single lost packet."""
        results = {'responses': [(1, 64, 0), (2, 64, 0), (4, 64, 0)],
                    'summary': {'transmitted': 4, 'received': 3},
                    }

        r = pingexp.find_lost_sequence_numbers(results)

        self.assertTrue(r == [3])


    def test_5(self):
        """Test single lost packet at the end."""
        results = {'responses': [(1, 64, 0), (2, 64, 0), (3, 64, 0)],
                    'summary': {'transmitted': 4, 'received': 3},
                    }

        r = pingexp.find_lost_sequence_numbers(results)

        self.assertTrue(r == [4])


    def test_6(self):
        """Test 3 lost packets at the end."""
        results = {'responses': [(1, 64, 0), (2, 64, 0), (3, 64, 0)],
                    'summary': {'transmitted': 6, 'received': 3},
                    }

        r = pingexp.find_lost_sequence_numbers(results)

        self.assertTrue(r == [4,5,6])


    def test_7(self):
        """Combined test."""
        results = {'responses': [(2, 64, 0), (3, 64, 0), (5, 64, 0), (6, 64, 0), (8,64,0), (9,64,0)],
                    'summary': {'transmitted': 12, 'received': 6},
                    }

        r = pingexp.find_lost_sequence_numbers(results)

        self.assertTrue(r == [1,4,7,10,11,12])


if __name__ == '__main__':
    unittest.main()
