from unittest import TestCase

from piccolo.columns.column_types import Array, BigInt, Integer
from piccolo.table import Table
from tests.base import engines_only, sqlite_only


class MyTable(Table):
    value = Array(base_column=Integer())


class TestArrayDefault(TestCase):
    def test_array_default(self):
        """
        We use ``ListProxy`` instead of ``list`` as a default, because of
        issues with Sphinx's autodoc. Make sure it's correctly converted to a
        plain ``list`` in ``Array.__init__``.
        """
        column = Array(base_column=Integer())
        self.assertTrue(column.default is list)


class TestArray(TestCase):
    """
    Make sure an Array column can be created, and work correctly.
    """

    def setUp(self):
        MyTable.create_table().run_sync()

    def tearDown(self):
        MyTable.alter().drop_table().run_sync()

    @engines_only("postgres", "sqlite")
    def test_storage(self):
        """
        Make sure data can be stored and retrieved.

        🐛 Cockroach bug: https://github.com/cockroachdb/cockroach/issues/71908 "could not decorrelate subquery" error under asyncpg

        """  # noqa: E501
        MyTable(value=[1, 2, 3]).save().run_sync()

        row = MyTable.objects().first().run_sync()
        assert row is not None
        self.assertEqual(row.value, [1, 2, 3])

    @engines_only("postgres")
    def test_index(self):
        """
        Indexes should allow individual array elements to be queried.

        🐛 Cockroach bug: https://github.com/cockroachdb/cockroach/issues/71908 "could not decorrelate subquery" error under asyncpg

        """  # noqa: E501
        MyTable(value=[1, 2, 3]).save().run_sync()

        self.assertEqual(
            MyTable.select(MyTable.value[0]).first().run_sync(), {"value": 1}
        )

    @engines_only("postgres")
    def test_all(self):
        """
        Make sure rows can be retrieved where all items in an array match a
        given value.

        🐛 Cockroach bug: https://github.com/cockroachdb/cockroach/issues/71908 "could not decorrelate subquery" error under asyncpg

        """  # noqa: E501
        MyTable(value=[1, 1, 1]).save().run_sync()

        self.assertEqual(
            MyTable.select(MyTable.value)
            .where(MyTable.value.all(1))
            .first()
            .run_sync(),
            {"value": [1, 1, 1]},
        )

        self.assertEqual(
            MyTable.select(MyTable.value)
            .where(MyTable.value.all(0))
            .first()
            .run_sync(),
            None,
        )

    @engines_only("postgres")
    def test_any(self):
        """
        Make sure rows can be retrieved where any items in an array match a
        given value.

        🐛 Cockroach bug: https://github.com/cockroachdb/cockroach/issues/71908 "could not decorrelate subquery" error under asyncpg

        """  # noqa: E501
        MyTable(value=[1, 2, 3]).save().run_sync()

        self.assertEqual(
            MyTable.select(MyTable.value)
            .where(MyTable.value.any(1))
            .first()
            .run_sync(),
            {"value": [1, 2, 3]},
        )

        self.assertEqual(
            MyTable.select(MyTable.value)
            .where(MyTable.value.any(0))
            .first()
            .run_sync(),
            None,
        )

    @engines_only("postgres")
    def test_cat(self):
        """
        Make sure values can be appended to an array.

        🐛 Cockroach bug: https://github.com/cockroachdb/cockroach/issues/71908 "could not decorrelate subquery" error under asyncpg

        """  # noqa: E501
        MyTable(value=[1, 1, 1]).save().run_sync()

        MyTable.update(
            {MyTable.value: MyTable.value.cat([2])}, force=True
        ).run_sync()

        self.assertEqual(
            MyTable.select().run_sync(), [{"id": 1, "value": [1, 1, 1, 2]}]
        )

        # Try plus symbol

        MyTable.update(
            {MyTable.value: MyTable.value + [3]}, force=True
        ).run_sync()

        self.assertEqual(
            MyTable.select().run_sync(), [{"id": 1, "value": [1, 1, 1, 2, 3]}]
        )

        # Make sure non-list values work

        MyTable.update(
            {MyTable.value: MyTable.value + 4}, force=True
        ).run_sync()

        self.assertEqual(
            MyTable.select().run_sync(),
            [{"id": 1, "value": [1, 1, 1, 2, 3, 4]}],
        )

    @sqlite_only
    def test_cat_sqlite(self):
        """
        If using SQLite then an exception should be raised currently.
        """
        with self.assertRaises(ValueError) as manager:
            MyTable.value.cat([2])

        self.assertEqual(
            str(manager.exception),
            "Only Postgres and Cockroach support array appending.",
        )


class NestedArrayTable(Table):
    value = Array(base_column=Array(base_column=BigInt()))


class TestNestedArray(TestCase):
    """
    Make sure that tables with nested arrays can be created, and work
    correctly.

    Related to this bug, with nested array columns containing ``BigInt``:

    https://github.com/piccolo-orm/piccolo/issues/936

    """

    def setUp(self):
        NestedArrayTable.create_table().run_sync()

    def tearDown(self):
        NestedArrayTable.alter().drop_table().run_sync()

    @engines_only("postgres", "sqlite")
    def test_storage(self):
        """
        Make sure data can be stored and retrieved.

        🐛 Cockroach bug: https://github.com/cockroachdb/cockroach/issues/71908 "could not decorrelate subquery" error under asyncpg

        """  # noqa: E501
        NestedArrayTable(value=[[1, 2, 3], [4, 5, 6]]).save().run_sync()

        row = NestedArrayTable.objects().first().run_sync()
        assert row is not None
        self.assertEqual(row.value, [[1, 2, 3], [4, 5, 6]])


class TestGetDimensions(TestCase):
    def test_get_dimensions(self):
        """
        Make sure that `_get_dimensions` returns the correct value.
        """
        self.assertEqual(Array(Integer())._get_dimensions(), 1)
        self.assertEqual(Array(Array(Integer()))._get_dimensions(), 2)
        self.assertEqual(Array(Array(Array(Integer())))._get_dimensions(), 3)


class TestGetInnerValueType(TestCase):
    def test_get_inner_value_type(self):
        """
        Make sure that `_get_inner_value_type` returns the correct base type.
        """
        self.assertEqual(Array(Integer())._get_inner_value_type(), int)
        self.assertEqual(Array(Array(Integer()))._get_inner_value_type(), int)
        self.assertEqual(
            Array(Array(Array(Integer())))._get_inner_value_type(), int
        )
