import bz2
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from conversation_corpus import Components, key, lines, partition, tag_row


class CorpusTests(unittest.TestCase):
    def test_publisher_detailed_tag_order(self):
        self.assertEqual(tag_row('2\t1088\tMUIRIEL\t2010-06-13 00:12:58'),(1088,2,'MUIRIEL','2010-06-13 00:12:58'))

    def test_transitive_and_duplicate_components_do_not_leak(self):
        graph=Components()
        graph.union(5,9); graph.union(12,4); graph.union(9,12)
        self.assertEqual({graph.root(i) for i in [4,5,9,12]}, {4})
        self.assertEqual(len({partition(graph.root(i)) for i in [4,5,9,12]}),1)
        # Membership is independent of edge input order.
        other=Components()
        for a,b in [(9,12),(12,4),(5,9)]: other.union(a,b)
        self.assertEqual([graph.root(i) for i in [4,5,9,12]], [other.root(i) for i in [4,5,9,12]])

    def test_normalization_keeps_distinct_words_and_scripts(self):
        self.assertEqual(key(' CAFÉ  au lait '),key('Cafe\u0301 au lait'))
        self.assertNotEqual(key('si'),key('sí'))
        self.assertNotEqual(key('吃饭'),key('吃飯'))

    def test_archive_paths_and_oversized_lines_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'archive.tar.bz2'
            for name in ('links.csv','../links.csv'):
                with tarfile.open(path,'w:bz2') as archive:
                    info=tarfile.TarInfo(name);info.size=4
                    archive.addfile(info,io.BytesIO(b'1\t2\n'))
                if name=='links.csv': self.assertEqual(list(lines(path,'links.csv')),['1\t2'])
                else:
                    with self.assertRaises(ValueError): list(lines(path,'links.csv'))
            path=Path(directory)/'large.bz2';path.write_bytes(bz2.compress(b'a'*65537))
            with self.assertRaises(ValueError): list(lines(path))

    def test_partition_recipe_is_stable_and_has_both_partitions(self):
        values=[partition(i) for i in range(1,10001)]
        self.assertEqual(values,[partition(i) for i in range(1,10001)])
        self.assertGreater(values.count('reserved'),1300)
        self.assertLess(values.count('reserved'),1700)


if __name__=='__main__': unittest.main()
