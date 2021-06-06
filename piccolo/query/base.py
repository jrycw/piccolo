from __future__ import annotations
import itertools
from time import time
import typing as t

from piccolo.querystring import QueryString
from piccolo.utils.sync import run_sync
from piccolo.utils.encoding import dump_json

if t.TYPE_CHECKING:  # pragma: no cover
    from piccolo.table import Table  # noqa


class Timer:
    def __enter__(self):
        self.start = time()

    def __exit__(self, exception_type, exception, traceback):
        self.end = time()
        print(f"Duration: {self.end - self.start}s")


class Query:

    __slots__ = ("table", "_frozen_querystrings")

    def __init__(
        self,
        table: t.Type[Table],
        frozen_querystrings: t.Optional[t.Sequence[QueryString]] = None,
    ):
        self.table = table
        self._frozen_querystrings = frozen_querystrings

    @property
    def engine_type(self) -> str:
        engine = self.table._meta.db
        if engine:
            return engine.engine_type
        else:
            raise ValueError("Engine isn't defined.")

    async def _process_results(self, results):
        if results:
            keys = results[0].keys()
            keys = [i.replace("$", ".") for i in keys]
            raw = [dict(zip(keys, i.values())) for i in results]
        else:
            raw = []

        if hasattr(self, "run_callback"):
            self.run_callback(raw)

        raw = await self.response_handler(raw)

        output = getattr(self, "output_delegate", None)

        if output:
            if output._output.as_objects:
                # When using .first() we get a single row, not a list
                # of rows.
                if type(raw) is list:
                    raw = [self.table(**columns) for columns in raw]
                elif raw is None:
                    pass
                else:
                    raw = self.table(**raw)
            elif type(raw) is list:
                if output._output.as_list:
                    if len(raw) == 0:
                        return []
                    else:
                        if len(raw[0].keys()) != 1:
                            raise ValueError(
                                "Each row returned more than one value"
                            )
                        else:
                            raw = list(
                                itertools.chain(*[j.values() for j in raw])
                            )
                if output._output.as_json:
                    raw = dump_json(raw)

        return raw

    def _validate(self):
        """
        Override in any subclasses if validation needs to be run before
        executing a query - for example, warning a user if they're about to
        delete all the data from a table.
        """
        pass

    def __await__(self):
        """
        If the user doesn't explicity call .run(), proxy to it as a
        convenience.
        """
        return self.run().__await__()

    async def run(self, in_pool=True):
        self._validate()

        engine = self.table._meta.db
        if not engine:
            raise ValueError(
                f"Table {self.table._meta.tablename} has no db defined in "
                "_meta"
            )

        if len(self.querystrings) == 1:
            results = await engine.run_querystring(
                self.querystrings[0], in_pool=in_pool
            )
            return await self._process_results(results)
        else:
            responses = []
            # TODO - run in a transaction
            for querystring in self.querystrings:
                results = await engine.run_querystring(
                    querystring, in_pool=in_pool
                )
                responses.append(await self._process_results(results))
            return responses

    def run_sync(self, timed=False, *args, **kwargs):
        """
        A convenience method for running the coroutine synchronously.
        """
        coroutine = self.run(*args, **kwargs, in_pool=False)

        if timed:
            with Timer():
                return run_sync(coroutine)
        else:
            return run_sync(coroutine)

    async def response_handler(self, response):
        """
        Subclasses can override this to modify the raw response returned by
        the database driver.
        """
        return response

    ###########################################################################

    @property
    def sqlite_querystrings(self) -> t.Sequence[QueryString]:
        raise NotImplementedError

    @property
    def postgres_querystrings(self) -> t.Sequence[QueryString]:
        raise NotImplementedError

    @property
    def default_querystrings(self) -> t.Sequence[QueryString]:
        raise NotImplementedError

    @property
    def querystrings(self) -> t.Sequence[QueryString]:
        """
        Calls the correct underlying method, depending on the current engine.
        """
        if self._frozen_querystrings is not None:
            return self._frozen_querystrings

        engine_type = self.engine_type
        if engine_type == "postgres":
            try:
                return self.postgres_querystrings
            except NotImplementedError:
                return self.default_querystrings
        elif engine_type == "sqlite":
            try:
                return self.sqlite_querystrings
            except NotImplementedError:
                return self.default_querystrings
        else:
            raise Exception(
                f"No querystring found for the {engine_type} engine."
            )

    ###########################################################################

    def freeze(self) -> FrozenQuery:
        """
        This is a performance optimisation when the same query is run
        repeatedly. For example:

        .. code-block: python

            TOP_BANDS = Band.select(
                Band.name
            ).order_by(
                Band.popularity,
                ascending=False
            ).limit(
                10
            ).output(
                as_json=True
            ).freeze()

            # In the corresponding view/endpoint of whichever web framework
            # you're using:
            async def top_bands(self, request):
                return await TOP_BANDS.run()

        It means that Piccolo doesn't have to work as hard each time the query
        is run to generate the corresponding SQL - some of it is cached. If the
        query is defined within the endpoint, it has to generate the SQL from
        scratch each time.

        Once a query is frozen, you can't apply any more clauses to it (where,
        limit, output etc).

        """
        # Copy the query, so we don't store any references to the original.
        query = self.__class__(
            table=self.table, frozen_querystrings=self.querystrings
        )
        return FrozenQuery(query=query)

    ###########################################################################

    def __str__(self) -> str:
        return "; ".join([i.__str__() for i in self.querystrings])


class FrozenQuery:
    def __init__(self, query: Query):
        self.query = query

    async def run(self, *args, **kwargs):
        return await self.query.run(*args, **kwargs)

    def run_sync(self, *args, **kwargs):
        return self.query.run_sync(*args, **kwargs)

    def __getattr__(self, name: str):
        if hasattr(self.query, name):
            raise AttributeError(
                f"This query is frozen - {name} is only available on "
                "unfrozen queries."
            )
        else:
            raise AttributeError("Unrecognised attribute name.")

    def __str__(self) -> str:
        return self.query.__str__()
