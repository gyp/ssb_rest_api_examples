__author__ = 'gyp'

import unittest
import urllib.parse, json
from merge_proxy import *

class SSBAPITests(unittest.TestCase):
    USERNAME = "foo"
    PASSWORD = "bar"
    LOGSPACE_NAME = "apple"

    def test_login_calls_one_request(self):
        requests = self._do_a_login_and_get_requests()
        self.assertEqual(len(requests), 1)

    def _do_a_login_and_get_requests(self):
        (connection, api) = self._get_connection_api_pair()
        api.login(self.USERNAME, self.PASSWORD)
        return connection.get_requests()

    def _get_connection_api_pair(self):
        connection = MockHTTPConnection()
        api = SSBAPI(connection)
        return connection, api

    def test_login_calls_a_post_to_the_login_point_in_the_api(self):
        (method, url, body, headers) = self._do_a_login_and_get_first_request()
        self.assertEqual("POST", method)
        self.assertEqual("/api/1/login", url)

    def _do_a_login_and_get_first_request(self):
        requests = self._do_a_login_and_get_requests()
        return requests[0]

    def test_login_calls_a_post_with_the_user_and_pass(self):
        (method, url, body, headers) = self._do_a_login_and_get_first_request()
        expected_body =  urllib.parse.urlencode({'username': self.USERNAME, 'password': self.PASSWORD})
        self.assertEqual(expected_body, body)

    def test_list_logspaces_proxies_list_logspaces(self):
        self._test_object_call_proxies_api_call(
            object_func="list_logspaces",
            api_url="/api/1/search/logspace/list_logspaces",
            response_value={"logspace1", "foo", "bar", "logspace4"}
        )

    def _test_object_call_proxies_api_call(self, object_func, api_url, args=(), response_value=None):
        (connection, api) = self._get_connection_api_pair()
        if response_value is not None:
            # the first one is for the login which we don't want to care about here
            connection.set_responses([None, self._generate_successful_response(response_value)])
        api.login(self.USERNAME, self.PASSWORD)

        func_to_call = getattr(api, object_func)
        result = func_to_call(*args)

        requests = connection.get_requests()
        self.assertEqual(len(requests), 2)  # again, the first one was the login
        (method, url, body, headers) = requests[1]
        self.assertEqual("GET", method)
        self._assertURLEqual(api_url, url)
        if response_value is not None:
            self.assertEqual(response_value, result)

    def _assertURLEqual(self, expected, actual):
        expected_parsed = urllib.parse.urlparse(expected)
        actual_parsed = urllib.parse.urlparse(actual)

        # these fields need to match char-by-char
        for field in ('scheme', 'netloc', 'path'):
            self.assertEqual(getattr(expected_parsed, field), getattr(actual_parsed, field))

        # but the sequence is not important in the query
        expected_query = urllib.parse.parse_qs(expected_parsed.query)
        actual_query = urllib.parse.parse_qs(actual_parsed.query)
        self.assertDictEqual(expected_query, actual_query)

    def _generate_successful_response(self, object_to_return):
        return "{\"result\": %s}" % self._object_to_json(object_to_return)

    def _object_to_json(self, object_to_convert):
        if type(object_to_convert) == type(set()):
            object_to_convert = list(object_to_convert)
        return json.dumps(object_to_convert)

    def test_logout_is_proxied_to_logout(self):
        self._test_object_call_proxies_api_call(
            object_func="logout",
            api_url="/api/1/logout",
        )

    def test_filter_proxies_filter(self):
        self._test_filter_type_command("filter", "filter",
                                       [{"logmsg1": "logvalue1"}, {"logmsg2": "logvalue2"}], True)

    def _test_filter_type_command(self, object_func, api_command_in_url, return_value, add_limit_offset):
        test_from = 123
        test_to = 456
        test_expression = "search_expression"
        test_offset = 222
        test_limit = 333

        expected_params = {'from': test_from, 'to': test_to, 'search_expression': test_expression}
        if add_limit_offset:
            expected_params["offset"] = test_offset
            expected_params["limit"] = test_limit

        expected_params = urllib.parse.urlencode(expected_params)

        self._test_object_call_proxies_api_call(
            object_func=object_func,
            args=(self.LOGSPACE_NAME, test_from, test_to, test_expression, test_offset, test_limit),
            api_url="/api/1/search/logspace/%s/%s?%s" % (api_command_in_url, self.LOGSPACE_NAME, expected_params),
            response_value=return_value
        )

    def test_number_of_messages_proxies_number_of_messages(self):
        self._test_filter_type_command("number_of_messages", "number_of_messages", 999, False)

    def test_auth_token_is_included_in_later_calls_after_login(self):
        (connection, api) = self._get_connection_api_pair()
        AUTH_TOKEN = "asdfasdfaqwerqwerqewr"

        connection.set_responses([
            self._generate_successful_response(AUTH_TOKEN),  # login
            self._generate_successful_response("fake_logspace"),  # list_logspaces
            self._generate_successful_response("[]"),  # filter
            self._generate_successful_response("[]"),  # number_of_messages
            None  # logout
        ])

        api.login(self.USERNAME, self.PASSWORD)
        api.list_logspaces()
        api.filter("fake_logspace", 123, 456)
        api.number_of_messages("fake_logspace", 123, 456)
        api.logout()

        requests = connection.get_requests()
        self.assertEqual(5, len(requests))  # just playing safe, we've tested this above
        for i in range(1, 5):
            (method, url, body, headers) = requests[i]
            self.assertTrue("Cookie" in headers)
            cookies = urllib.parse.unquote(headers['Cookie'])
            self.assertEqual("AUTHENTICATION_TOKEN=%s" % AUTH_TOKEN, headers['Cookie'])


class MockHTTPConnection:
    def __init__(self):
        self.requests = []
        self.responses = []

    # utility funcs for testing

    def set_responses(self, responses):
        self.responses = responses

    def get_requests(self):
        return self.requests

    # mock HTTPConnection interface

    def request(self, method, url, body=None, headers={}):
        self.requests.append((method, url, body, headers))

    def getresponse(self):
        if len(self.responses) > 0:
            response_data = self.responses.pop(0)

        if response_data is None:
            response_data = ""

        return MockHTTPResponse(200, response_data)

    def close(self):
        pass


class MockHTTPResponse:
    def __init__(self, status, data):
        self.status = status
        self.data = str.encode(data)

    def read(self):
        return self.data

    def readall(self):
        return self.read()


class KWayMergeTests(unittest.TestCase):
    def test_next_throws_exception_if_fetch_functions_is_not_iterable(self):
        with self.assertRaises(TypeError):
            merger = KWayMerger(1)
            merger.next()

    def test_next_throws_exception_if_fetch_functions_are_not_callable(self):
        with self.assertRaises(TypeError):
            merger = KWayMerger((1, 2))
            merger.next()

    def test_next_returns_the_single_value_from_a_single_call(self):
        MAGIC = 123456
        simplefetcher = lambda: MAGIC
        merger = KWayMerger((simplefetcher,))
        self.assertEqual(MAGIC, merger.next())

    def test_first_next_returns_the_first_from_10(self):
        fetchers = []
        for i in range(10):
            fetchers.append(MockFetcher([i]).next)
        merger = KWayMerger(tuple(fetchers))
        self.assertEqual(0, merger.next())

    def test_two_elements_are_sorted_well(self):
        merger = KWayMerger((MockFetcher([2]).next, MockFetcher([1]).next))

        self.assertEqual(1, merger.next())
        self.assertEqual(2, merger.next())

    def test_one_ordered_list_is_returned_as_is(self):
        merger = KWayMerger((MockFetcher(list(range(10))).next,))

        for i in range(10):
            self.assertEqual(merger.next(), i)

    def test_multiple_identical_lists_are_merged_propery(self):
        LIST_LENGTH = 5
        NUMBER_OF_LISTS = 10

        fetchers = []
        for i in range(NUMBER_OF_LISTS):
            fetchers.append(MockFetcher(list(range(LIST_LENGTH))).next)

        merger = KWayMerger(tuple(fetchers))

        for i in range(LIST_LENGTH):
            for j in range(NUMBER_OF_LISTS):
                self.assertEqual(merger.next(), i)

    def test_zipper_merge_works(self):
        LIST_LENGTH = 50
        NUMBER_OF_LISTS = 200

        fetchers = []
        for i in range(NUMBER_OF_LISTS):
            start = i
            step = NUMBER_OF_LISTS
            end = start + NUMBER_OF_LISTS * LIST_LENGTH
            fetchers.append(MockFetcher(list(range(start, end, step))).next)

        merger = KWayMerger(tuple(fetchers))

        for i in range(LIST_LENGTH * NUMBER_OF_LISTS):
            self.assertEqual(i, merger.next())


class MockFetcher:
    def __init__(self, list_to_return):
        self._list_to_return = list_to_return

    def next(self):
        if len(self._list_to_return) > 0:
            return self._list_to_return.pop(0)
        else:
            return None

    #TODO_fetches_are_not_called_multiple_times

class MergeProxyTest(unittest.TestCase):
    LOGSPACE_NAME = "testlogspacename"

    def test_class_can_be_initialized_with_a_tuple_of_SSBs(self):
        MergeProxy((MockSSB(), MockSSB()))

    def test_list_logspaces_with_a_single_SSB_is_passed_through(self):
        test_logspaces = {"logspace1", "logspace2", "logspace3"}
        ssb = MockSSB()
        ssb.set_logspaces(test_logspaces)

        proxy = MergeProxy((ssb, ))

        self.assertEqual(test_logspaces, proxy.list_logspaces())

    def test_list_logspaces_results_are_merged_from_two_SSBs(self):
        test_logspaces_1 = {"logspace1", "logspace2", "logspace3"}
        test_logspaces_2 = {"logspace1", "logspace2",              "logspace4"}
        merged_result =    {"logspace1", "logspace2", "logspace3", "logspace4"}

        ssb1 = MockSSB()
        ssb2 = MockSSB()
        ssb1.set_logspaces(test_logspaces_1)
        ssb2.set_logspaces(test_logspaces_2)
        proxy = MergeProxy((ssb1, ssb2))

        self.assertSetEqual(merged_result, proxy.list_logspaces())

    def test_list_logspaces_merges_from_lots_of_SSBs(self):
        ssbs = []
        for i in range(10):
            new_ssb = MockSSB()
            logspaces = set(range(i+1))
            new_ssb.set_logspaces(logspaces)
            ssbs.append(new_ssb)
        ssbs = tuple(ssbs)

        proxy = MergeProxy(ssbs)

        self.assertSetEqual(set(range(10)), proxy.list_logspaces())

    def test_number_of_messages_is_passed_through_if_theres_a_single_SSB(self):
        NUMBER_OF_MESSAGES = 999

        ssb = MockSSB()
        ssb.set_number_of_messages(NUMBER_OF_MESSAGES)

        proxy = MergeProxy((ssb, ))

        self.assertEqual(NUMBER_OF_MESSAGES, proxy.number_of_messages(self.LOGSPACE_NAME))

    def test_number_of_messages_params_are_passed_through(self):
        TEST_FROM = 123
        TEST_TO = 456
        TEST_EXPRESSION = "text expression"

        ssb = MockSSB()
        proxy = MergeProxy((ssb, ))

        proxy.number_of_messages(self.LOGSPACE_NAME, TEST_FROM, TEST_TO, TEST_EXPRESSION)

        calls = ssb.get_calls()
        self.assertEqual(1, len(calls))
        self.assertEqual("number_of_messages", calls[0]['func'])
        self.assertTupleEqual((self.LOGSPACE_NAME, TEST_FROM, TEST_TO, TEST_EXPRESSION), calls[0]['args'])

    def test_number_of_messages_is_added_from_multiple_SSBs(self):
        ssbs = []
        expected_sum = 0
        for i in range(10):
            new_ssb = MockSSB()
            new_num_messages = pow(i, 3)
            new_ssb.set_number_of_messages(new_num_messages)
            expected_sum += new_num_messages
            ssbs.append(new_ssb)

        proxy = MergeProxy(tuple(ssbs))

        self.assertEqual(expected_sum, proxy.number_of_messages(self.LOGSPACE_NAME))

    def test_filter_is_passed_through_if_theres_a_single_SSB(self):
        LOGS = [{'processed_timestamp': 123, 'message': "testmessage"}]

        ssb = MockSSB()
        ssb.set_logs(LOGS)

        proxy = MergeProxy((ssb, ))

        self.assertListEqual(LOGS, proxy.filter(self.LOGSPACE_NAME))

    def test_filter_params_are_passed_through(self):
        TEST_FROM = 123
        TEST_TO = 456
        TEST_EXPRESSION = "text expression"

        ssb = MockSSB()
        proxy = MergeProxy((ssb, ))

        proxy.filter(self.LOGSPACE_NAME, TEST_FROM, TEST_TO, TEST_EXPRESSION)

        calls = ssb.get_calls()
        self.assertEqual(1, len(calls))
        self.assertEqual("filter", calls[0]['func'])
        # NOTE: this is nasty and only passes because we pass offset and limit as kwargs... but hey, it's a PoC :)
        self.assertTupleEqual((self.LOGSPACE_NAME, TEST_FROM, TEST_TO, TEST_EXPRESSION), calls[0]['args'])

    def test_filter_result_count_is_sum_of_underlying_SSBs(self):
        ssbs = []
        expected_log_count = 0

        for i in range(10):
            new_ssb = MockSSB()
            new_logs = []
            for j in range(i):
                new_logs.append({'processed_timestamp': 0, 'id': j})

            expected_log_count += len(new_logs)
            new_ssb.set_logs(new_logs)
            ssbs.append(new_ssb)

        proxy = MergeProxy(tuple(ssbs))

        self.assertEqual(expected_log_count, len(proxy.filter(self.LOGSPACE_NAME, limit=(expected_log_count*2))))

    def test_filter_results_contain_all_the_elements_from_the_underlying_SSBs(self):
        ssbs = []
        expected_ids = set()

        for i in range(10):
            new_ssb = MockSSB()
            new_logs = []
            for j in range(100):
                new_id = "ssb%d log%i" % (i, j)
                expected_ids.add(new_id)
                new_logs.append({'processed_timestamp': 0, 'id': new_id})

            new_ssb.set_logs(new_logs)
            ssbs.append(new_ssb)

        proxy = MergeProxy(tuple(ssbs))

        # comparing them as sets will work because we gave them unique ids
        merged_results = proxy.filter(self.LOGSPACE_NAME, limit=len(expected_ids)*2)
        actual_ids = set()
        for result in merged_results:
            actual_ids.add(result['id'])

        self.assertSetEqual(expected_ids, actual_ids)

    def test_filter_results_are_ascending_according_to_processed_timestamp_but_per_ssb_order_is_retained(self):
        ssbs = []

        # The logs are ordered in overlapping but ascending sequence is guaranteed in
        # each of the lists
        num_of_ssbs = 10
        for i in range(num_of_ssbs):
            new_ssb = MockSSB()
            new_logs = []
            timestamp_base = num_of_ssbs*10 - 3*i
            for j in range(100):
                timestamp = timestamp_base + 2 * j
                # we add two logs with the same timestamp to be able to check if the orginal ordering is retained
                new_logs.append({'processed_timestamp': timestamp, 'host': i, 'id': 2*j})
                new_logs.append({'processed_timestamp': timestamp, 'host': i, 'id': 2*j+1})
            new_ssb.set_logs(new_logs)
            ssbs.append(new_ssb)

        proxy = MergeProxy(tuple(ssbs))
        merged_results = proxy.filter(self.LOGSPACE_NAME)

        previous_log = None
        previous_ids = {}
        for i in range(num_of_ssbs):
            previous_ids[i] = None

        for current_log in merged_results:
            if previous_log is not None:
                self.assertGreaterEqual(current_log['processed_timestamp'], previous_log['processed_timestamp'])
            if previous_ids[current_log['host']] is not None:
                self.assertGreater(current_log['id'], previous_ids[current_log['host']])
            previous_log = current_log
            previous_ids[current_log['host']] = current_log['id']

    def test_filter_returns_limit_number_of_elements(self):
        ssbs = []
        limit_to_test = 25
        for i in range(10):
            new_ssb = MockSSB()
            logs_per_ssb = limit_to_test * 2
            new_logs = [{'processed_timestamp': 0}] * logs_per_ssb
            new_ssb.set_logs(new_logs)
            ssbs.append(new_ssb)

        proxy = MergeProxy(tuple(ssbs))

        self.assertEqual(limit_to_test, len(proxy.filter(self.LOGSPACE_NAME, limit=limit_to_test)))


class MockSSB():
    def __init__(self):
        self.logspaces = set()
        self.calls = []
        self._number_of_messages = 0
        self._logs = []

    def set_logspaces(self, logspaces):
        self._logspaces = logspaces

    def set_logs(self, logs):
        self._logs = logs

    def set_number_of_messages(self, number_of_messages):
        self._number_of_messages = number_of_messages

    def get_calls(self):
        return self.calls

    def number_of_messages(self, *args, **kwargs):
        self.calls.append({"func": "number_of_messages", "args": args, "kwarg": kwargs})
        return self._number_of_messages

    def filter(self, *args, **kwargs):
        self.calls.append({"func": "filter", "args": args, "kwarg": kwargs})
        return self._logs

    def list_logspaces(self):
        return self._logspaces

class MergeProxyConfigTest(unittest.TestCase):
    def test_get_servers_returns_a_list(self):
        servers = self._feed_with_sample_2_server_config_and_return_what_get_servers_returns()
        self.assertEqual(type(list()), type(servers))

    def _feed_with_sample_2_server_config_and_return_what_get_servers_returns(self):
        config_text = """
[server1.serverhost]
user=a
password=a
[1.2.3.4]
user=a
password=a
"""
        config = MergeProxyConfig(config_text)
        return config.get_servers()

    def test_returns_all_servers(self):
        servers = self._feed_with_sample_2_server_config_and_return_what_get_servers_returns()
        self.assertEqual(2, len(servers))

    def test_all_returned_servers_are_objects_with_user_and_pass_fields(self):
        servers = self._feed_with_sample_2_server_config_and_return_what_get_servers_returns()
        for server in servers:
            self.assertEqual(type({}), type(server))

if __name__ == '__main__':
    unittest.main()
