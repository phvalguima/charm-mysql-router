# Copyright 2019-2021 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy
import collections
import json
import mock

import charms_openstack.test_utils as test_utils

import charm.openstack.mysql_router as mysql_router


class TestMySQLRouterProperties(test_utils.PatchHelper):

    def setUp(self):
        super().setUp()
        self.cls = mock.MagicMock()
        self.patch_object(mysql_router.ch_core.hookenv, "local_unit")
        self.patch_object(mysql_router.ch_net_ip, "get_relation_ip")

    def test_shared_db_address(self):
        _addr = "127.0.0.1"
        self.assertEqual(
            mysql_router.shared_db_address(self.cls), _addr)

    def test_db_router_address(self):
        _addr = "10.10.10.30"
        self.get_relation_ip.return_value = _addr
        self.assertEqual(
            mysql_router.db_router_address(self.cls), _addr)
        self.get_relation_ip.assert_called_once_with("db-router")


class FakeException(Exception):

    def __init__(self, *args, **kwargs):
        pass

    @property
    def output(self):
        return "Mocked Exception".encode("UTF-8")

    @property
    def code(self):
        return 1


class TestMySQLRouterCharm(test_utils.PatchHelper):

    def setUp(self):
        super().setUp()
        self.patch_object(mysql_router, "os")
        self.patch_object(mysql_router, "subprocess")
        self.patch_object(mysql_router.reactive.flags, "set_flag")
        self.patch_object(mysql_router.reactive.flags, "clear_flag")
        self.patch_object(
            mysql_router.reactive.relations, "endpoint_from_flag")
        self.patch_object(mysql_router.ch_net_ip, "get_relation_ip")
        self.patch_object(mysql_router.ch_core.hookenv, "local_unit")
        self.patch_object(mysql_router.ch_core.host, "adduser")
        self.patch_object(mysql_router.ch_core.host, "add_group")
        self.patch_object(mysql_router.ch_core.host, "user_exists")
        self.patch_object(mysql_router.ch_core.host, "group_exists")
        self.patch_object(mysql_router.ch_core.host, "mkdir")
        self.patch_object(mysql_router.ch_core.host, "cmp_pkgrevno")
        self.patch_object(mysql_router.ch_net_ip, "resolve_network_cidr")

        self.stdout = mock.MagicMock()
        self.subprocess.STDOUT = self.stdout
        self.subprocess.PIPE = self.stdout

        self.patch_object(
            mysql_router.mysql, "get_db_data")
        self.get_db_data.side_effect = self._fake_get_db_data

        self.db_router = mock.MagicMock()
        self.shared_db = mock.MagicMock()

        self.mock_unprefixed = "UNPREFIXED"
        self.keystone_shared_db = mock.MagicMock()
        self.keystone_shared_db.relation_id = "shared-db:5"
        self.nova_shared_db = mock.MagicMock()
        self.nova_shared_db.relation_id = "shared-db:20"
        # Keystone shared-db
        self.keystone_unit_name = "keystone/7"
        self.keystone_unit_ip = "10.10.10.70"
        self.keystone_unit = mock.MagicMock()
        self.keystone_unit.unit_name = self.keystone_unit_name
        self.keystone_unit.relation = self.keystone_shared_db
        self.keystone_shared_db.joined_units = [self.keystone_unit]
        self.keystone_shared_db.all_joined_units.received = {
            "database": "keystone", "username": "keystone",
            "hostname": self.keystone_unit_ip}
        self.keystone_shared_db.all_joined_units.__getitem__.return_value = (
            self.keystone_unit)
        self.keystone_shared_db.relations = {
            self.keystone_shared_db.relation_id: self.keystone_shared_db}
        # Nova shared-db
        self.nova_unit_name = "nova/12"
        self.nova_unit_ip = "10.20.20.70"
        self.nova_unit = mock.MagicMock()
        self.nova_unit.unit_name = self.nova_unit_name
        self.nova_unit.relation = self.nova_shared_db
        self.nova_shared_db.joined_units = [self.nova_unit]
        self.nova_shared_db.all_joined_units.received = {
            "nova_database": "nova", "nova_username": "nova",
            "nova_hostname": self.nova_unit_ip,
            "novaapi_database": "nova_api", "novaapi_username": "nova",
            "novaapi_hostname": self.nova_unit_ip,
            "novacell0_database": "nova_cell0", "novacell0_username": "nova",
            "novacell0_hostname": self.nova_unit_ip}
        self.nova_shared_db.all_joined_units.__getitem__.return_value = (
            self.nova_unit)
        self.nova_shared_db.relations = {
            self.nova_shared_db.relation_id: self.nova_shared_db}

        self.mock_open = mock.mock_open()
        self.patch('builtins.open', new_callable=self.mock_open)

    def _fake_get_allowed_units(self, interface):
        return " ".join(
            [x.unit_name for x in
                interface.joined_units])

    def _fake_get_db_data(self, relation_data, unprefixed=None):
        # This "fake" get_db_data looks a lot like the real thing.
        # Charmhelpers is mocked out entirely and attempting to
        # mock the output made the test setup more difficult.
        settings = copy.deepcopy(relation_data)
        databases = collections.OrderedDict()

        singleset = {"database", "username", "hostname"}
        if singleset.issubset(settings):
            settings["{}_{}".format(unprefixed, "hostname")] = (
                settings["hostname"])
            settings.pop("hostname")
            settings["{}_{}".format(unprefixed, "database")] = (
                settings["database"])
            settings.pop("database")
            settings["{}_{}".format(unprefixed, "username")] = (
                settings["username"])
            settings.pop("username")

        for k, v in settings.items():
            db = k.split("_")[0]
            x = "_".join(k.split("_")[1:])
            if db not in databases:
                databases[db] = collections.OrderedDict()
            databases[db][x] = v

        return databases

    def test_mysqlrouter_bin(self):
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.mysqlrouter_bin,
            "/usr/bin/mysqlrouter")

    def test_db_router_endpoint(self):
        self.endpoint_from_flag.return_value = self.db_router
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.db_router_endpoint,
            self.db_router)

    def test_db_prefix(self):
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.db_prefix,
            "mysqlrouter")

    def test_db_router_user(self):
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.db_router_user,
            "mysqlrouteruser")

    def test_db_router_password(self):
        _json_pass = '"clusterpass"'
        _pass = "clusterpass"
        self.endpoint_from_flag.return_value = self.db_router
        self.db_router.password.return_value = _json_pass
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.db_router_password,
            _pass)

    def test_db_router_address(self):
        _addr = "10.10.10.30"
        self.subprocess.check_output.return_value = \
            b'10.10.10.10 dev eth0 src 10.10.10.30 uid 1000\n    cache'
        # IP in the same network as .30
        self.endpoint_from_flag.return_value = self.db_router
        self.db_router.db_host.return_value = '"10.10.10.10"'
        self.get_relation_ip.return_value = _addr
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.db_router_address,
            _addr)

    def test_db_router_address_with_fan_network(self):
        # mysql-router has eth0 -> 10.10.10.30 and fan-252 -> 252.0.10.20
        _addr = "10.10.10.30"
        self.subprocess.check_output.return_value = \
            b'252.0.10.10 dev eth0 src 252.0.10.20 uid 1000\n    cache'
        # First call returns the network for relation_ip which corresponds
        # to the relation and the second call returns the subnet for the
        # fan subnet.
        self.resolve_network_cidr.side_effect = [
            "10.10.10.0/24", "252.0.10.0/24"]
        self.endpoint_from_flag.return_value = self.db_router
        # IP of the database in the fan-network
        self.db_router.db_host.return_value = '"252.0.10.10"'
        self.get_relation_ip.return_value = _addr
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.db_router_address,
            "252.0.10.20")

        # Now, check the case where fan-net is crossing nodes.
        # That will render two nodes with two subnets in 252.0.0.0/8
        # Each node will have its own /24 share of the fan-network cidr.
        self.subprocess.check_output.reset_mock()
        self.resolve_network_cidr.reset_mock()
        # There is a gateway now, which is the host IP
        self.subprocess.check_output.return_value = \
            b'252.0.10.10 via 252.0.10.1 dev eth0 src 252.0.10.20 uid 1000\n    cache' # noqa
        # First call returns the network for relation_ip which corresponds
        # to the relation and the second call returns the subnet for the
        # fan subnet.
        self.resolve_network_cidr.side_effect = [
            "252.0.20.0/24", "252.0.10.0/24"]
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.db_router_address,
            "252.0.10.20")

    def test_cluster_address(self):
        _json_addr = '"10.10.10.50"'
        _addr = "10.10.10.50"
        self.endpoint_from_flag.return_value = self.db_router
        self.db_router.db_host.return_value = _json_addr
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.cluster_address,
            _addr)

    def test_shared_db_address(self):
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.shared_db_address,
            "127.0.0.1")

    def test_mysqlrouter_working_dir(self):
        mrc = mysql_router.MySQLRouterCharm()
        _name = "keystone-mysql-router"
        mrc.name = _name
        self.assertEqual(
            mrc.mysqlrouter_working_dir,
            "/var/lib/mysql/{}".format(_name))

    def test_mysqlrouter_home_dir(self):
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.mysqlrouter_home_dir,
            "/var/lib/mysql")

    def test_mysqlrouter_group(self):
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.mysqlrouter_group,
            "mysql")

    def test_mysqlrouter_user(self):
        mrc = mysql_router.MySQLRouterCharm()
        self.assertEqual(
            mrc.mysqlrouter_user,
            "mysql")

    def test_install(self):
        self.patch_object(
            mysql_router.charms_openstack.charm.OpenStackCharm,
            "install", "super_install")
        _name = "keystone-mysql-router"
        self.patch_object(mysql_router.ch_core.templating, "render")
        self.os.path.exists.return_value = False
        self.group_exists.return_value = False
        self.user_exists.return_value = False
        mrc = mysql_router.MySQLRouterCharm()
        mrc.configure_source = mock.MagicMock()
        mrc.name = _name
        mrc.install()
        self.super_install.assert_called_once()
        mrc.configure_source.assert_called_once()
        self.add_group.assert_called_once_with("mysql", system_group=True)
        self.adduser.assert_called_once_with(
            "mysql", home_dir="/var/lib/mysql", primary_group="mysql",
            shell="/usr/sbin/nologin", system_user=True)
        self.mkdir.assert_called_once_with(
            "/var/lib/mysql", group="mysql", owner="mysql", perms=0o755)

        self.render.assert_called_once()
        self.subprocess.check_output.assert_called_once_with(
            ['systemctl', 'enable', _name],
            stderr=self.subprocess.STDOUT)

    def test_get_db_helper(self):
        self.patch_object(
            mysql_router.mysql, "MySQL8Helper")
        _helper = mock.MagicMock()
        _json_addr = '"10.10.10.70"'
        _json_pass = '"clusterpass"'
        self.endpoint_from_flag.return_value = self.db_router
        self.db_router.db_host.return_value = _json_addr
        self.db_router.password.return_value = _json_pass
        mrc = mysql_router.MySQLRouterCharm()
        self.MySQL8Helper.return_value = _helper
        self.assertEqual(_helper, mrc.get_db_helper())
        self.MySQL8Helper.assert_called_once()

    def test_states_to_check(self):
        self.patch_object(
            mysql_router.charms_openstack.charm.OpenStackCharm,
            "states_to_check", "super_states")
        self.super_states.return_value = {}
        _required_rels = ["shared-db", "db-router"]
        mrc = mysql_router.MySQLRouterCharm()
        _results = mrc.states_to_check(_required_rels)
        _states_to_check = [x[0] for x in _results["charm"]]
        self.super_states.assert_called_once_with(_required_rels)
        self.assertTrue(
            mysql_router.MYSQL_ROUTER_BOOTSTRAPPED in _states_to_check)
        self.assertTrue(
            mysql_router.MYSQL_ROUTER_STARTED in _states_to_check)
        self.assertTrue(
            mysql_router.DB_ROUTER_PROXY_AVAILABLE in _states_to_check)

    def test_check_mysql_connection(self):
        self.patch_object(
            mysql_router.mysql, "MySQL8Helper")
        _helper = mock.MagicMock()
        _json_pass = '"clusterpass"'
        _pass = "clusterpass"
        _user = "mysqlrouteruser"
        _addr = "127.0.0.1"
        _port = 3316
        _connect_timeout = 30
        self.endpoint_from_flag.return_value = self.db_router
        self.db_router.password.return_value = _json_pass

        self.patch_object(
            mysql_router.mysql.MySQLdb, "_exceptions")
        self._exceptions.OperationalError = Exception
        _helper = mock.MagicMock()
        mrc = mysql_router.MySQLRouterCharm()
        mrc.options.base_port = _port
        mrc.get_db_helper = mock.MagicMock()
        mrc.get_db_helper.return_value = _helper

        # Connects
        self.assertTrue(mrc.check_mysql_connection())
        _helper.connect.assert_called_once_with(
            _user, _pass, _addr, port=_port, connect_timeout=_connect_timeout)

        # Fails
        _helper.reset_mock()
        _helper.connect.side_effect = self._exceptions.OperationalError
        self.assertFalse(mrc.check_mysql_connection())
        _helper.connect.assert_called_once_with(
            _user, _pass, _addr, port=_port, connect_timeout=_connect_timeout)

    def test_custom_assess_status_check(self):
        _check = mock.MagicMock()
        _check.return_value = None, None
        _conn_check = mock.MagicMock()
        _conn_check.return_value = True

        # All is well
        mrc = mysql_router.MySQLRouterCharm()
        mrc.check_if_paused = _check
        mrc.check_interfaces = _check
        mrc.check_mandatory_config = _check
        mrc.check_mysql_connection = _conn_check

        self.assertEqual((None, None), mrc.custom_assess_status_check())
        self.assertEqual(3, len(_check.mock_calls))
        _conn_check.assert_called_once_with()

        # First checks fail
        _check.return_value = "blocked", "for some reason"
        self.assertEqual(
            ("blocked", "for some reason"),
            mrc.custom_assess_status_check())

        # MySQL connect fails
        _check.return_value = None, None
        _conn_check.return_value = False
        self.assertEqual(
            ("blocked", "Failed to connect to MySQL"),
            mrc.custom_assess_status_check())

    def test_bootstrap_mysqlrouter(self):
        _json_addr = '"10.10.10.60"'
        _json_pass = '"clusterpass"'
        _pass = json.loads(_json_pass)
        _addr = json.loads(_json_addr)
        _user = "mysql"
        _port = "3006"
        self.patch_object(mysql_router.reactive.flags, "is_flag_set")
        self.endpoint_from_flag.return_value = self.db_router
        self.db_router.password.return_value = _json_pass
        self.db_router.db_host.return_value = _json_addr
        self.is_flag_set.return_value = False

        mrc = mysql_router.MySQLRouterCharm()
        mrc.options.system_user = _user
        mrc.options.base_port = _port

        # Successful < 8.0.22
        self.cmp_pkgrevno.return_value = -1
        mrc.bootstrap_mysqlrouter()
        self.subprocess.check_output.assert_has_calls([
            mock.call(['ip', 'route', 'get', '10.10.10.60']),
            mock.call().decode('utf-8'),
            mock.call().decode().__contains__('via'),
            mock.call().decode().split(),
            mock.call().decode().split().__getitem__(4),
            mock.call().decode().split().__getitem__().__bool__(),
            mock.call(
                [mrc.mysqlrouter_bin, "--user", _user,
                 "--name", mrc.name,
                 "--bootstrap", "{}:{}@{}"
                 .format(mrc.db_router_user, _pass, _addr),
                 "--directory", mrc.mysqlrouter_working_dir,
                 "--conf-use-sockets",
                 "--conf-bind-address", mrc.shared_db_address,
                 "--report-host", mrc.db_router_address,
                 "--conf-base-port", _port], stderr=self.stdout),
            mock.call(['ip', 'route', 'get', '10.10.10.60']),
            mock.call().decode('utf-8'),
            mock.call().decode().__contains__('via'),
            mock.call().decode().split(),
            mock.call().decode().split().__getitem__(4),
            mock.call().decode().split().__getitem__().__bool__()])
        self.set_flag.assert_has_calls([
            mock.call(mysql_router.MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED),
            mock.call(mysql_router.MYSQL_ROUTER_BOOTSTRAPPED)])
        self.clear_flag.assert_called_once_with(
            mysql_router.MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED)

        # Successful >= 8.0.22
        self.subprocess.reset_mock()
        self.set_flag.reset_mock()
        self.clear_flag.reset_mock()
        self.cmp_pkgrevno.return_value = 1
        mrc.bootstrap_mysqlrouter()
        self.subprocess.check_output.assert_has_calls([
            mock.call(['ip', 'route', 'get', '10.10.10.60']),
            mock.call().decode('utf-8'),
            mock.call().decode().__contains__('via'),
            mock.call().decode().split(),
            mock.call().decode().split().__getitem__(4),
            mock.call().decode().split().__getitem__().__bool__(),
            mock.call(
                [mrc.mysqlrouter_bin, "--user", _user,
                 "--name", mrc.name,
                 "--bootstrap", "{}:{}@{}"
                 .format(mrc.db_router_user, _pass, _addr),
                 "--directory", mrc.mysqlrouter_working_dir,
                 "--conf-use-sockets",
                 "--conf-bind-address", mrc.shared_db_address,
                 "--report-host", mrc.db_router_address,
                 "--conf-base-port", _port,
                 "--disable-rest"],
                stderr=self.stdout),
            mock.call(['ip', 'route', 'get', '10.10.10.60']),
            mock.call().decode('utf-8'),
            mock.call().decode().__contains__('via'),
            mock.call().decode().split(),
            mock.call().decode().split().__getitem__(4),
            mock.call().decode().split().__getitem__().__bool__()])
        self.set_flag.assert_has_calls([
            mock.call(mysql_router.MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED),
            mock.call(mysql_router.MYSQL_ROUTER_BOOTSTRAPPED)])
        self.clear_flag.assert_called_once_with(
            mysql_router.MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED)

        # First attempt fail
        self.subprocess.reset_mock()
        self.set_flag.reset_mock()
        self.subprocess.CalledProcessError = FakeException
        self.subprocess.check_output.side_effect = (
            self.subprocess.CalledProcessError)
        mrc.bootstrap_mysqlrouter()
        self.set_flag.assert_called_once_with(
            mysql_router.MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED)

        # Bail
        self.subprocess.reset_mock()
        self.set_flag.reset_mock()
        self.is_flag_set.return_value = True
        mrc.bootstrap_mysqlrouter()
        self.subprocess.check_output.assert_not_called()

        # Second attempt success
        self.subprocess.reset_mock()
        self.set_flag.reset_mock()
        self.clear_flag.reset_mock()
        self.cmp_pkgrevno.return_value = 1
        self.is_flag_set.side_effect = [False, True]
        self.subprocess.check_output.side_effect = None
        mrc.bootstrap_mysqlrouter()
        self.subprocess.check_output.assert_has_calls([
            mock.call(['ip', 'route', 'get', '10.10.10.60']),
            mock.call().decode('utf-8'),
            mock.call().decode().__contains__('via'),
            mock.call().decode().split(),
            mock.call().decode().split().__getitem__(4),
            mock.call().decode().split().__getitem__().__bool__(),
            mock.call(
                [mrc.mysqlrouter_bin, "--user", _user,
                 "--name", mrc.name,
                 "--bootstrap", "{}:{}@{}"
                 .format(mrc.db_router_user, _pass, _addr),
                 "--directory", mrc.mysqlrouter_working_dir,
                 "--conf-use-sockets",
                 "--conf-bind-address", mrc.shared_db_address,
                 "--report-host", mrc.db_router_address,
                 "--conf-base-port", _port,
                 "--disable-rest", "--force"],
                stderr=self.stdout),
            mock.call(['ip', 'route', 'get', '10.10.10.60']),
            mock.call().decode('utf-8'),
            mock.call().decode().__contains__('via'),
            mock.call().decode().split(),
            mock.call().decode().split().__getitem__(4),
            mock.call().decode().split().__getitem__().__bool__()])
        self.set_flag.assert_has_calls([
            mock.call(mysql_router.MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED),
            mock.call(mysql_router.MYSQL_ROUTER_BOOTSTRAPPED)])
        self.clear_flag.assert_called_once_with(
            mysql_router.MYSQL_ROUTER_BOOTSTRAP_ATTEMPTED)

    def test_start_mysqlrouter(self):
        self.patch_object(mysql_router.ch_core.host, "service_start")
        _name = "keystone-mysql-router"
        mrc = mysql_router.MySQLRouterCharm()
        mrc.name = _name

        mrc.start_mysqlrouter()
        self.service_start.assert_called_once_with(_name)
        self.set_flag.assert_called_once_with(
            mysql_router.MYSQL_ROUTER_STARTED)

    def test_stop_mysqlrouter(self):
        _name = "keystone-mysql-router"
        self.patch_object(mysql_router.ch_core.host, "service_stop")
        mrc = mysql_router.MySQLRouterCharm()
        mrc.name = _name

        mrc.stop_mysqlrouter()
        self.service_stop.assert_called_once_with(_name)

    def test_restart_mysqlrouter(self):
        _name = "keystone-mysql-router"
        mrc = mysql_router.MySQLRouterCharm()
        mrc.name = _name
        self.patch_object(mysql_router.ch_core.host, "service_restart")

        mrc.restart_mysqlrouter()
        self.service_restart.assert_called_once_with(_name)

    def test_proxy_db_and_user_requests_no_prefix(self):
        mrc = mysql_router.MySQLRouterCharm()
        mrc.proxy_db_and_user_requests(self.keystone_shared_db, self.db_router)
        self.db_router.configure_proxy_db.assert_called_once_with(
            'keystone', 'keystone', self.keystone_unit_ip,
            prefix=mrc._unprefixed)

    def test_proxy_db_and_user_requests_prefixed(self):
        mrc = mysql_router.MySQLRouterCharm()
        mrc.proxy_db_and_user_requests(self.nova_shared_db, self.db_router)
        _calls = [
            mock.call('nova', 'nova', self.nova_unit_ip, prefix="nova"),
            mock.call('nova_api', 'nova', self.nova_unit_ip,
                      prefix="novaapi"),
            mock.call('nova_cell0', 'nova', self.nova_unit_ip,
                      prefix="novacell0")]
        self.db_router.configure_proxy_db.assert_has_calls(
            _calls, any_order=True)

    def test_proxy_db_and_user_responses_unprefixed(self):
        _wait_time = 90
        _json_wait_time = "90"
        _json_pass = '"pass"'
        _pass = json.loads(_json_pass)
        _json_ca = '"Certificate Authority"'
        _ca = json.loads(_json_ca)
        _local_unit = "kmr/5"
        _port = 3316
        self.db_router.password.return_value = _json_pass
        self.local_unit.return_value = _local_unit

        mrc = mysql_router.MySQLRouterCharm()
        mrc.options.base_port = _port
        self.db_router.get_prefixes.return_value = [
            mrc._unprefixed, mrc.db_prefix]

        # Allowed Units,  wait_time and ssl_ca unset
        self.db_router.wait_timeout.return_value = None
        self.db_router.ssl_ca.return_value = None
        self.db_router.allowed_units.return_value = '""'

        mrc.proxy_db_and_user_responses(
            self.db_router, self.keystone_shared_db)
        self.keystone_shared_db.set_db_connection_info.assert_called_once_with(
            self.keystone_shared_db.relation_id, mrc.shared_db_address,
            _pass, allowed_units=None, prefix=None, wait_timeout=None,
            db_port=_port, ssl_ca=None)

        # Allowed Units and wait time set correctly
        self.db_router.wait_timeout.return_value = _json_wait_time
        self.db_router.ssl_ca.return_value = _json_ca
        self.keystone_shared_db.set_db_connection_info.reset_mock()
        self.db_router.allowed_units.return_value = json.dumps(_local_unit)
        mrc.proxy_db_and_user_responses(
            self.db_router, self.keystone_shared_db)

        self.keystone_shared_db.set_db_connection_info.assert_called_once_with(
            self.keystone_shared_db.relation_id, mrc.shared_db_address,
            _pass, allowed_units=self.keystone_unit_name, prefix=None,
            wait_timeout=_wait_time, db_port=_port, ssl_ca=_ca)

        # Confirm msyqlrouter credentials are not sent over the shared-db
        # relation
        for call in self.keystone_shared_db.set_db_connection_info.mock_calls:
            self.assertNotEqual(mrc.db_prefix, call.kwargs.get("prefix"))

    def test_proxy_db_and_user_responses_prefixed(self):
        _wait_time = 90
        _json_wait_time = "90"
        _json_pass = '"pass"'
        _pass = json.loads(_json_pass)
        _json_ca = '"Certificate Authority"'
        _ca = json.loads(_json_ca)
        _local_unit = "nmr/5"
        _nova = "nova"
        _novaapi = "novaapi"
        _novacell0 = "novacell0"
        _port = 3316
        self.db_router.password.return_value = _json_pass
        self.local_unit.return_value = _local_unit

        mrc = mysql_router.MySQLRouterCharm()
        mrc.options.base_port = _port
        self.db_router.get_prefixes.return_value = [
            mrc.db_prefix, _nova, _novaapi, _novacell0]

        # Allowed Units,  wait time and CA unset
        self.db_router.wait_timeout.return_value = None
        self.db_router.ssl_ca.return_value = None
        self.db_router.allowed_units.return_value = '""'
        mrc.proxy_db_and_user_responses(self.db_router, self.nova_shared_db)
        _calls = [
            mock.call(
                self.nova_shared_db.relation_id, mrc.shared_db_address, _pass,
                allowed_units=None, prefix=_nova,
                wait_timeout=None, db_port=_port, ssl_ca=None),
            mock.call(
                self.nova_shared_db.relation_id, mrc.shared_db_address, _pass,
                allowed_units=None, prefix=_novaapi,
                wait_timeout=None, db_port=_port, ssl_ca=None),
            mock.call(
                self.nova_shared_db.relation_id, mrc.shared_db_address, _pass,
                allowed_units=None, prefix=_novacell0,
                wait_timeout=None, db_port=_port, ssl_ca=None),
        ]
        self.nova_shared_db.set_db_connection_info.assert_has_calls(
            _calls, any_order=True)

        # Allowed Units and wait time set correctly
        self.db_router.wait_timeout.return_value = _json_wait_time
        self.db_router.ssl_ca.return_value = _json_ca
        self.nova_shared_db.set_db_connection_info.reset_mock()
        self.db_router.allowed_units.return_value = json.dumps(_local_unit)
        mrc.proxy_db_and_user_responses(self.db_router, self.nova_shared_db)
        _calls = [
            mock.call(
                self.nova_shared_db.relation_id, mrc.shared_db_address, _pass,
                allowed_units=self.nova_unit_name, prefix=_nova,
                wait_timeout=_wait_time, db_port=_port, ssl_ca=_ca),
            mock.call(
                self.nova_shared_db.relation_id, mrc.shared_db_address, _pass,
                allowed_units=self.nova_unit_name, prefix=_novaapi,
                wait_timeout=_wait_time, db_port=_port, ssl_ca=_ca),
            mock.call(
                self.nova_shared_db.relation_id, mrc.shared_db_address, _pass,
                allowed_units=self.nova_unit_name, prefix=_novacell0,
                wait_timeout=_wait_time, db_port=_port, ssl_ca=_ca),
        ]
        self.nova_shared_db.set_db_connection_info.assert_has_calls(
            _calls, any_order=True)

        # Confirm msyqlrouter credentials are not sent over the shared-db
        # relation
        for call in self.nova_shared_db.set_db_connection_info.mock_calls:
            self.assertNotEqual(mrc.db_prefix, call.kwargs.get("prefix"))

    def test_proxy_db_and_user_responses_no_data(self):
        self.db_router.password.return_value = None

        mrc = mysql_router.MySQLRouterCharm()
        self.db_router.get_prefixes.return_value = [
            mrc._unprefixed, mrc.db_prefix]
        mrc.proxy_db_and_user_responses(
            self.db_router, self.keystone_shared_db)
        self.keystone_shared_db.set_db_connection_info.assert_not_called()

    def test_update_config_parameters(self):
        self.patch_object(mysql_router.configparser, "ConfigParser")

        _mock_config_parser = mock.MagicMock()
        self.ConfigParser.return_value = _mock_config_parser

        _params = {"DEFAULT": {"client_ssl_mode": "PREFERRED"}}

        mrc = mysql_router.MySQLRouterCharm()
        mrc.update_config_parameters(_params)
        _mock_config_parser.read.assert_called_once()
        _mock_config_parser.__getitem__.assert_called_once_with('DEFAULT')
        _mock_config_parser.__getitem__().__setitem__.assert_called_once_with(
            'client_ssl_mode', 'PREFERRED')
        _mock_config_parser.write.assert_called_once_with(
            self.mock_open()().__enter__())

    def test_update_config_parameters_missing_heading(self):
        # test fix for Bug LP#1927981
        class FakeConfigParser(dict):
            def read(*args, **kwargs):
                pass

            def write(*args, **kwargs):
                pass

        current_config = {"DEFAULT": {"client_ssl_mode": "NONE"}}
        fake_config = FakeConfigParser(current_config)

        self.patch_object(mysql_router.configparser, "ConfigParser",
                          return_value=fake_config)

        # metadata_cache:jujuCluster didn't exist in the previous config so the
        # header needs to be created (c.f. BUG LP#1927981)
        _params = {
            "DEFAULT": {"client_ssl_mode": "PREFERRED"},
            "metadata_cache:jujuCluster": {"thing": "a-thing"},
        }

        mrc = mysql_router.MySQLRouterCharm()
        # should not throw a key error.
        mrc.update_config_parameters(_params)
        self.assertIn('metadata_cache:jujuCluster', fake_config)
        self.assertEqual(fake_config['metadata_cache:jujuCluster'],
                         {"thing": "a-thing"})

    def test_config_changed(self):
        _config_data = {
            "ttl": '5',
            "auth_cache_ttl": '10',
            "auth_cache_refresh_interval": '7',
        }

        def _fake_config(key=None):
            return _config_data[key] if key else _config_data

        self.patch_object(mysql_router.ch_core.hookenv, "config")
        self.patch_object(mysql_router.os.path, "exists")
        self.patch_object(mysql_router.ch_core.host, "restart_on_change")
        self.config.side_effect = _fake_config
        self.endpoint_from_flag.return_value = self.db_router

        _mock_update_config_parameters = mock.MagicMock()
        mrc = mysql_router.MySQLRouterCharm()
        mrc.name = 'foobar'
        mrc.update_config_parameters = _mock_update_config_parameters

        _params = {
            'metadata_cache:jujuCluster': _config_data,
            'DEFAULT': {
                'client_ssl_mode': "PASSTHROUGH",
                'pid_file': '/run/mysql/mysqlrouter-foobar.pid'
            },
        }

        # Not bootstrapped yet
        self.exists.return_value = False
        mrc.config_changed()
        _mock_update_config_parameters.assert_not_called()

        # With TLS PASSTHROUGH
        self.db_router.ssl_ca.return_value = '"CACERT"'
        self.exists.return_value = True
        mrc.config_changed()
        _mock_update_config_parameters.assert_called_once_with(_params)

        # With TLS PREFERRED
        self.db_router.ssl_ca.return_value = None
        _params["DEFAULT"]["client_ssl_mode"] = "PREFERRED"
        self.exists.return_value = True
        _mock_update_config_parameters.reset_mock()
        mrc.config_changed()
        _mock_update_config_parameters.assert_called_once_with(_params)

    def test_custom_restart_function(self):
        self.patch_object(mysql_router.ch_core.host, "service_stop")
        self.patch_object(mysql_router.ch_core.host, "service_start")
        self.service_name = "mysql-router"
        _mock_check_mysql_connection = mock.MagicMock()

        mrc = mysql_router.MySQLRouterCharm()
        mrc.check_mysql_connection = _mock_check_mysql_connection

        mrc.custom_restart_function(self.service_name)
        self.service_stop.assert_called_once_with(self.service_name)
        self.service_start.assert_called_once_with(self.service_name)
        _mock_check_mysql_connection.assert_called_once()
