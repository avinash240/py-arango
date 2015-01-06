"""ArangoDB Database."""

from arango.utils import camelify, uncamelify
from arango.batch import Batch
from arango.graph import Graph
from arango.collection import Collection
from arango.exceptions import *
from arango.cursor import CursorFactory


class Database(CursorFactory):
    """A wrapper around database specific API.

    :param name: the name of this database
    :type name: str
    :param api: ArangoDB API object
    :type api: arango.api.ArangoAPI
    """

    def __init__(self, name, api):
        self.name = name
        self._api = api
        self._collection_cache = {}
        self._graph_cache = {}
        self.batch = Batch(self._api)

    def _update_collection_cache(self):
        """Invalidate the collection cache."""
        real_cols = set(self.collections["all"])
        cached_cols = set(self._collection_cache)
        for col_name in cached_cols - real_cols:
            del self._collection_cache[col_name]
        for col_name in real_cols - cached_cols:
            self._collection_cache[col_name] = Collection(
                name=col_name, api=self._api
            )

    def _update_graph_cache(self):
        """Invalidate the graph cache."""
        real_graphs = set(self.graphs)
        cached_graphs = set(self._graph_cache)
        for graph_name in cached_graphs - real_graphs:
            del self._graph_cache[graph_name]
        for graph_name in real_graphs - cached_graphs:
            self._graph_cache[graph_name] = Graph(
                name=graph_name, api=self._api
            )

    @property
    def properties(self):
        """Return all properties of this database.

        :returns: the database properties
        :rtype: dict
        :raises: ArangoDatabasePropertyError
        """
        res = self._api.get("/_api/database/current")
        if res.status_code != 200:
            raise ArangoDatabasePropertyError(res)
        return uncamelify(res.obj["result"])

    @property
    def id(self):
        """Return the ID of this database.

        :returns: the database ID
        :rtype: str
        :raises: ArangoDatabasePropertyError
        """
        return self.properties["id"]

    @property
    def path(self):
        """Return the file path of this database.

        :returns: the file path of this database
        :rtype: str
        :raises: ArangoDatabasePropertyError
        """
        return self.properties["path"]

    @property
    def is_system(self):
        """Return True if this is a system database, False otherwise.

        :returns: True if this is a system database, False otherwise
        :rtype: bool
        :raises: ArangoDatabasePropertyError
        """
        return self.properties["is_system"]

    ###########
    # Queries #
    ###########

    def explain_query(self, query, all_plans=False, max_plans=None,
                      optimizer_rules=None):
        """Explain the AQL query.

        This method does not execute the query, but only inspect it and
        return meta information about it.

        If ``all_plans`` is set to True, all possible execution plans are
        returned. Otherwise only the optimal plan is returned.

        For more information on optimizer_rules, please refer to:
        https://docs.arangodb.com/HttpAqlQuery/README.html

        :param query: the AQL query to explain
        :type query: str
        :param all_plans: whether or not to return all execution plans
        :type all_plans: bool
        :param max_plans: maximum number of plans the optimizer generates
        :type max_plans: None or int
        :param optimizer_rules: list of optimizer rules
        :type optimizer_rules: list
        :returns: the query plan or list of plans (if all_plans is True)
        :rtype: dict or list
        :raises: ArangoQueryExplainError
        """
        options = {"allPlans": all_plans}
        if max_plans is not None:
            options["maxNumberOfPlans"] = max_plans
        if optimizer_rules is not None:
            options["optimizer"] = {"rules": optimizer_rules}
        res = self._api.post(
            "/_api/explain", data={"query": query, "options": options}
        )
        if res.status_code != 200:
            raise ArangoQueryExplainError(res)
        if "plan" in res.obj:
            return uncamelify(res.obj["plan"])
        else:
            return uncamelify(res.obj["plans"])


    def validate_query(self, query):
        """Validate the AQL query.

        :param query: the AQL query to validate
        :type query: str
        :raises: ArangoQueryValidateError
        """
        res = self._api.post("/_api/query", data={"query": query})
        if res.status_code != 200:
            raise ArangoQueryValidateError(res)

    def execute_query(self, query, count=False, batch_size=None, ttl=None,
                      bind_vars=None, full_count=None, max_plans=None,
                      optimizer_rules=None):
        """Execute the AQL query and return the result.

        For more information on ``full_count`` please refer to:
        https://docs.arangodb.com/HttpAqlQueryCursor/AccessingCursors.html

        :param query: the AQL query to execute
        :type query: str
        :param count: whether or not the document count should be returned
        :type count: bool
        :param batch_size: maximum number of documents in one roundtrip
        :type batch_size: int
        :param ttl: time-to-live for the cursor (in seconds)
        :type ttl: int
        :param bind_vars: key/value list of bind parameters
        :type bind_vars: list
        :param full_count: whether or not to include count before last LIMIT
        :param max_plans: maximum number of plans the optimizer generates
        :type max_plans: None or int
        :param optimizer_rules: list of optimizer rules
        :type optimizer_rules: list
        :returns: the cursor from executing the query
        :raises: ArangoQueryExecuteError, ArangoCursorDeleteError
        """
        options = {}
        if full_count is not None:
            options["fullCount"] = full_count
        if max_plans is not None:
            options["maxNumberOfPlans"] = max_plans
        if optimizer_rules is not None:
            options["optimizer"] = {"rules": optimizer_rules}

        data = {
            "query": query,
            "count": count,
        }
        if batch_size is not None:
            data["batchSize"] = batch_size
        if ttl is not None:
            data["ttl"] = ttl
        if bind_vars is not None:
            data["bindVars"] = bind_vars
        if options:
            data["options"] = options

        res = self._api.post("/_api/cursor", data=data)
        if res.status_code != 201:
            raise ArangoQueryExecuteError(res)
        return self.cursor(res)

    ########################
    # Handling Collections #
    ########################

    @property
    def collections(self):
        """Return the names of the collections in this database.

        :returns: the names of the collections
        :rtype: dict
        :raises: ArangoCollectionListError
        """
        res = self._api.get("/_api/collection")
        if res.status_code != 200:
            raise ArangoCollectionListError(res)

        user_collections = []
        system_collections = []
        for collection in res.obj["collections"]:
            if collection["isSystem"]:
                system_collections.append(collection["name"])
            else:
                user_collections.append(collection["name"])
        return {
            "user": user_collections,
            "system": system_collections,
            "all": user_collections + system_collections,
        }

    def col(self, name):
        """Alias for self.collection."""
        return self.collection(name)

    def collection(self, name):
        """Return the Collection object of the specified name.

        :param name: the name of the collection
        :type name: str
        :returns: the requested collection object
        :rtype: arango.collection.Collection
        :raises: TypeError, ArangoCollectionNotFound
        """
        if not isinstance(name, str):
            raise TypeError("Expecting a str.")
        if name in self._collection_cache:
            return self._collection_cache[name]
        else:
            self._update_collection_cache()
            if name not in self._collection_cache:
                raise ArangoCollectionNotFoundError(name)
            return self._collection_cache[name]

    def add_collection(self, name, wait_for_sync=False, do_compact=True,
                       journal_size=None, is_system=False, is_volatile=False,
                       key_generator_type="traditional", allow_user_keys=True,
                       key_increment=None, key_offset=None, is_edge=False,
                       number_of_shards=None, shard_keys=None):
        """Add a new collection to this database.

        :param name: name of the new collection
        :type name: str
        :param wait_for_sync: whether or not to wait for sync to disk
        :type wait_for_sync: bool
        :param do_compact: whether or not the collection is compacted
        :type do_compact: bool
        :param journal_size: the max size of the journal or datafile
        :type journal_size: int
        :param is_system: whether or not the collection is a system collection
        :type is_system: bool
        :param is_volatile: whether or not the collection is in-memory only
        :type is_volatile: bool
        :param key_generator_type: ``traditional`` or ``autoincrement``
        :type key_generator_type: str
        :param allow_user_keys: whether or not to allow users to supply keys
        :type allow_user_keys: bool
        :param key_increment: increment value for ``autoincrement`` generator
        :type key_increment: int
        :param key_offset: initial offset value for ``autoincrement`` generator
        :type key_offset: int
        :param is_edge: whether or not the collection is an edge collection
        :type is_edge: bool
        :param number_of_shards: the number of shards to create
        :type number_of_shards: int
        :param shard_keys: the attribute(s) used to determine the target shard
        :type shard_keys: list
        :raises: ArangoCollectionAddError
        """
        key_options = {
            "type": key_generator_type,
            "allowUserKeys": allow_user_keys
        }
        if key_increment is not None:
            key_options["increment"] = key_increment
        if key_offset is not None:
            key_options["offset"] = key_offset
        data = {
            "name": name,
            "waitForSync": wait_for_sync,
            "doCompact": do_compact,
            "isSystem": is_system,
            "isVolatile": is_volatile,
            "type": 3 if is_edge else 2,
            "keyOptions": key_options
        }
        if journal_size is not None:
            data["journalSize"] = journal_size
        if number_of_shards is not None:
            data["numberOfShards"] = number_of_shards
        if shard_keys is not None:
            data["shardKeys"] = shard_keys

        res = self._api.post("/_api/collection", data=data)
        if res.status_code != 200:
            raise ArangoCollectionAddError(res)
        self._update_collection_cache()
        return self.collection(name)

    def remove_collection(self, name):
        """Remove the specified collection from this database.

        :param name: the name of the collection to remove
        :type name: str
        :raises: ArangoCollectionRemoveError
        """
        res = self._api.delete("/_api/collection/{}".format(name))
        if res.status_code != 200:
            raise ArangoCollectionRemoveError(res)
        self._update_collection_cache()

    def rename_collection(self, name, new_name):
        """Rename the specified collection in this database.

        :param name: the name of the collection to rename
        :type name: str
        :param new_name: the new name for the collection
        :type new_name: str
        :raises: ArangoCollectionRenameError
        """
        res = self._api.put(
            "/_api/collection/{}/rename".format(name),
            data={"name": new_name}
        )
        if res.status_code != 200:
            raise ArangoCollectionRenameError(res)
        self._update_collection_cache()

    ##########################
    # Handling AQL Functions #
    ##########################

    @property
    def aql_functions(self):
        """Return the AQL functions defined in this database.

        :returns: a mapping of AQL function names to its javascript code
        :rtype: dict
        :raises: ArangoAQLFunctionListError
        """
        res = self._api.get("/_api/aqlfunction")
        if res.status_code != 200:
            raise ArangoAQLFunctionListError(res)
        return {func["name"]: func["code"]for func in res.obj}

    def add_aql_function(self, name, code):
        """Add a new AQL function.

        :param name: the name of the new AQL function to add
        :type name: str
        :param code: the stringified javascript code of the new function
        :type code: str
        :returns: the updated AQL functions
        :rtype: dict
        :raises: ArangoAQLFunctionAddError
        """
        data = {"name": name, "code": code}
        res = self._api.post("/_api/aqlfunction", data=data)
        if res.status_code not in (200, 201):
            raise ArangoAQLFunctionAddError(res)
        return self.aql_functions

    def remove_aql_function(self, name, group=None):
        """Remove an existing AQL function.

        If ``group`` is set to True, then the function name provided in
        ``name`` is treated as a namespace prefix, and all functions in
        the specified namespace will be deleted. If set to False, the
        function name provided in ``name`` must be fully qualified,
        including any namespaces.

        :param name: the name of the AQL function to remove
        :type name: str
        :param group: whether or not to treat name as a namespace prefix
        :returns: the updated AQL functions
        :rtype: dict
        :raises: ArangoAQLFunctionRemoveError
        """
        res = self._api.delete(
            "/_api/aqlfunction/{}".format(name),
            params={"group": group} if group is not None else {}
        )
        if res.status_code != 200:
            raise ArangoAQLFunctionRemoveError(res)
        return self.aql_functions

    ################
    # Transactions #
    ################

    def execute_transaction(self, collections=None, action=None):
        """Execute the transaction and return the result.

        The ``collections`` dict can only have keys ``write`` or ``read``
        with str or list as values. The values must be name(s) of collections
        that exist in this database.

        :param collections: the collections read/modified
        :type collections: dict
        :param action: the ArangoDB commands (in javascript) to be executed
        :type action: str
        :returns: the result from executing the transaction
        :rtype: dict
        :raises: ArangoTransactionExecuteError
        """
        data = {
            collections: {} if collections is None else collections,
            action: "" if action is None else ""
        }
        res = self._api.post("/_api/transaction", data=data)
        if res != 200:
            raise ArangoTransactionExecuteError(res)
        return res.obj["result"]

    ###################
    # Handling Graphs #
    ###################

    @property
    def graphs(self):
        """List all graphs in this database.

        :returns: the graphs in this database
        :rtype: dict
        :raises: ArangoGraphGetError
        """
        res = self._api.get("/_api/gharial")
        if res.status_code not in (200, 202):
            raise ArangoGraphListError(res)
        return [graph["_key"] for graph in res.obj["graphs"]]

    def graph(self, name):
        """Return the Graph object of the specified name.

        :param name: the name of the graph
        :type name: str
        :returns: the requested graph object
        :rtype: arango.graph.Graph
        :raises: TypeError, ArangoGraphNotFound
        """
        if not isinstance(name, str):
            raise TypeError("Expecting a str.")
        if name in self._graph_cache:
            return self._graph_cache[name]
        else:
            self._update_graph_cache()
            if name not in self._graph_cache:
                raise ArangoGraphNotFoundError(name)
            return self._graph_cache[name]

    def add_graph(self, name, edge_definitions=None,
                  orphan_collections=None):
        """Add a new graph in this database.

        # TODO expand on edge_definitions and orphan_collections

        :param name: name of the new graph
        :type name: str
        :param edge_definitions: definitions for edges
        :type edge_definitions: list
        :param orphan_collections: names of additional vertex collections
        :type orphan_collections: list
        :returns: the graph object
        :rtype: arango.graph.Graph
        :raises: ArangoGraphAddError
        """
        data = {"name": name}
        if edge_definitions is not None:
            data["edgeDefinitions"] = edge_definitions
        if orphan_collections is not None:
            data["orphanCollections"] = orphan_collections

        res = self._api.post("/_api/gharial", data=data)
        if res.status_code != 201:
            raise ArangoGraphAddError(res)
        self._update_graph_cache()
        return self.graph(name)

    def remove_graph(self, name):
        """Delete the graph of the given name from this database.

        :param name: the name of the graph to remove
        :type name: str
        :raises: ArangoGraphRemoveError
        """
        res = self._api.delete("/_api/gharial/{}".format(name))
        if res.status_code != 200:
            raise ArangoGraphRemoveError(res)
        self._update_graph_cache()
