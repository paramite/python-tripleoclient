#   Copyright 2019 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#
from json.decoder import JSONDecodeError
import os

from unittest import mock
from unittest import TestCase

from tripleoclient import export


class TestExport(TestCase):
    def setUp(self):
        self.unlink_patch = mock.patch('os.unlink')
        self.addCleanup(self.unlink_patch.stop)
        self.unlink_patch.start()
        self.mock_log = mock.Mock('logging.getLogger')

        outputs = [
            {'output_key': 'EndpointMap',
             'output_value': dict(em_key='em_value')},
            {'output_key': 'HostsEntry',
             'output_value': 'hosts entry'},
            {'output_key': 'GlobalConfig',
             'output_value': dict(gc_key='gc_value')},
        ]
        self.mock_stack = mock.Mock()
        self.mock_stack.to_dict.return_value = dict(outputs=outputs)
        self.mock_open = mock.mock_open(read_data='{"an_key":"an_value"}')

        mock_environment = mock.Mock()
        self.mock_stack.environment = mock_environment
        mock_environment.return_value = dict(
            parameter_defaults=dict())

        ceph_inv = {
            'DistributedComputeHCI': {
                'hosts': {
                    'dcn0-distributedcomputehci-0': {
                        'foo_ip': '192.168.24.42'
                    },
                    'dcn0-distributedcomputehci-1': {
                        'foo_ip': '192.168.8.8'
                    }
                }
            },
            'mons': {
                'children': {
                    'DistributedComputeHCI': {}
                }
            }
        }
        self.mock_open_ceph_inv = mock.mock_open(read_data=str(ceph_inv))

        ceph_global = {
            'service_net_map': {
                'ceph_mon_network': 'storage'
            }
        }
        self.mock_open_ceph_global = mock.mock_open(read_data=str(ceph_global))

        ceph_all = {
            'cluster': 'dcn0',
            'fsid': 'a5a22d37-e01f-4fa0-a440-c72585c7487f',
            'keys': [
                {'name': 'client.openstack'}
            ]
        }
        self.mock_open_ceph_all = mock.mock_open(read_data=str(ceph_all))

    @mock.patch('tripleoclient.utils.os.path.exists',
                autospec=True, reutrn_value=True)
    @mock.patch('tripleoclient.utils.get_stack')
    def test_export_stack(self, mock_get_stack, mock_exists):
        heat = mock.Mock()
        mock_get_stack.return_value = self.mock_stack
        with mock.patch('tripleoclient.utils.open', self.mock_open):
            data = export.export_stack(heat, "overcloud")

        expected = \
            {'AllNodesExtraMapData': {u'an_key': u'an_value'},
             'AuthCloudName': 'overcloud',
             'EndpointMapOverride': {'em_key': 'em_value'},
             'ExtraHostFileEntries': 'hosts entry',
             'GlobalConfigExtraMapData': {'gc_key': 'gc_value'}}

        self.assertEqual(expected, data)
        self.mock_open.assert_called_once_with(
            os.path.join(
                os.environ.get('HOME'),
                'config-download/overcloud/group_vars/overcloud.json'),
            'r')

    @mock.patch('tripleoclient.utils.os.path.exists',
                autospec=True, reutrn_value=True)
    @mock.patch('tripleoclient.utils.get_stack')
    def test_export_stack_auth_cloud_name_set(
            self, mock_get_stack, mock_exists):
        heat = mock.Mock()
        mock_get_stack.return_value = self.mock_stack
        self.mock_stack.environment.return_value['parameter_defaults'] = (
            dict(AuthCloudName='central'))
        with mock.patch('tripleoclient.utils.open', self.mock_open):
            data = export.export_stack(heat, "overcloud")

        expected = \
            {'AllNodesExtraMapData': {u'an_key': u'an_value'},
             'AuthCloudName': 'central',
             'EndpointMapOverride': {'em_key': 'em_value'},
             'ExtraHostFileEntries': 'hosts entry',
             'GlobalConfigExtraMapData': {'gc_key': 'gc_value'}}

        self.assertEqual(expected, data)
        self.mock_open.assert_called_once_with(
            os.path.join(
                os.environ.get('HOME'),
                'config-download/overcloud/group_vars/overcloud.json'),
            'r')

    @mock.patch('tripleoclient.utils.os.path.exists',
                autospec=True, reutrn_value=True)
    @mock.patch('tripleoclient.utils.get_stack')
    def test_export_stack_should_filter(self, mock_get_stack, mock_exists):
        heat = mock.Mock()
        mock_get_stack.return_value = self.mock_stack
        self.mock_open = mock.mock_open(
            read_data='{"an_key":"an_value","ovn_dbs_vip":"vip"}')
        with mock.patch('builtins.open', self.mock_open):
            data = export.export_stack(heat, "overcloud", should_filter=True)

        expected = \
            {'AllNodesExtraMapData': {u'ovn_dbs_vip': u'vip'},
             'AuthCloudName': 'overcloud',
             'EndpointMapOverride': {'em_key': 'em_value'},
             'ExtraHostFileEntries': 'hosts entry',
             'GlobalConfigExtraMapData': {'gc_key': 'gc_value'}}

        self.assertEqual(expected, data)
        self.mock_open.assert_called_once_with(
            os.path.join(
                os.environ.get('HOME'),
                'config-download/overcloud/group_vars/overcloud.json'),
            'r')

    @mock.patch('tripleoclient.utils.os.path.exists',
                autospec=True, reutrn_value=True)
    @mock.patch('tripleoclient.utils.get_stack')
    def test_export_stack_cd_dir(self, mock_get_stack, mock_exists):
        heat = mock.Mock()
        mock_get_stack.return_value = self.mock_stack
        with mock.patch('tripleoclient.utils.open', self.mock_open):
            export.export_stack(heat, "overcloud",
                                config_download_dir='/foo')
        self.mock_open.assert_called_once_with(
            '/foo/overcloud/group_vars/overcloud.json', 'r')

    @mock.patch('tripleoclient.utils.os.path.exists',
                autospec=True, reutrn_value=True)
    @mock.patch('tripleoclient.utils.get_stack')
    def test_export_stack_stack_name(self, mock_get_stack, mock_exists):
        heat = mock.Mock()
        mock_get_stack.return_value = self.mock_stack
        with mock.patch('tripleoclient.utils.open', self.mock_open):
            export.export_stack(heat, "control")
        mock_get_stack.assert_called_once_with(heat, 'control')

    @mock.patch('tripleoclient.utils.LOG.error', autospec=True)
    @mock.patch('tripleoclient.utils.json.load', autospec=True,
                side_effect=JSONDecodeError)
    @mock.patch('tripleoclient.utils.open')
    @mock.patch('tripleoclient.utils.os.path.exists', autospec=True,
                return_value=True)
    @mock.patch('tripleoclient.utils.get_stack', autospec=True)
    def test_export_stack_decode_error(self, mock_get_stack, mock_exists,
                                       mock_open, mock_json_load, mock_log):

        heat = mock.MagicMock()
        mock_get_stack.return_value = self.mock_stack
        self.assertRaises(
            RuntimeError, export.export_stack, heat, "overcloud")

        mock_open.assert_called_once_with(
            os.path.join(
                os.environ.get('HOME'),
                'config-download/overcloud/group_vars/overcloud.json'),
            'r')

    @mock.patch('tripleoclient.export.LOG')
    @mock.patch('tripleo_common.utils.plan.generate_passwords')
    def test_export_passwords(self, mock_gen_pass, mock_log):
        heat = mock.Mock()
        mock_passwords = {
            'AdminPassword': 'A',
            'RpcPassword': 'B',
            'CephClientKey': 'cephkey',
            'CephClusterFSID': 'cephkey',
            'CephRgwKey': 'cephkey'}

        mock_gen_pass.return_value = mock_passwords

        expected_password_export = mock_passwords.copy()
        data = export.export_passwords(heat, 'overcloud', False)

        self.assertEqual(
            expected_password_export,
            data)

    @mock.patch('tripleoclient.export.LOG')
    @mock.patch('tripleo_common.utils.plan.generate_passwords')
    def test_export_passwords_excludes(self, mock_gen_pass, mock_log):
        heat = mock.Mock()
        mock_passwords = {
            'AdminPassword': 'A',
            'RpcPassword': 'B',
            'CephClientKey': 'cephkey',
            'CephClusterFSID': 'cephkey',
            'CephRgwKey': 'cephkey'}

        mock_gen_pass.return_value = mock_passwords

        expected_password_export = {
            'AdminPassword': 'A',
            'RpcPassword': 'B'}

        data = export.export_passwords(heat, 'overcloud')

        self.assertEqual(expected_password_export, data)

    def test_export_ceph_net_key(self):
        with mock.patch('builtins.open', self.mock_open_ceph_global):
            mon_key = export.export_ceph_net_key('dcn0',
                                                 config_download_dir='/foo')
        self.assertEqual(mon_key, 'storage_ip')
        self.mock_open_ceph_global.assert_called_once_with(
            '/foo/dcn0/global_vars.yaml', 'r')

    def test_export_storage_ips(self):
        with mock.patch('builtins.open', self.mock_open_ceph_inv):
            storage_ips = export.export_storage_ips('dcn0',
                                                    config_download_dir='/foo',
                                                    ceph_net_key='foo_ip')
        self.assertEqual(storage_ips, ['192.168.24.42', '192.168.8.8'])
        self.mock_open_ceph_inv.assert_called_once_with(
            '/foo/dcn0/ceph-ansible/inventory.yml', 'r')

    def test_export_ceph(self):
        expected = {
            'external_cluster_mon_ips': '192.168.24.42',
            'keys': [
                {'name': 'client.openstack'}
            ],
            'ceph_conf_overrides': {
                'client': {
                    'keyring': '/etc/ceph/dcn0.client.openstack.keyring'
                }
            },
            'cluster': 'dcn0',
            'fsid': 'a5a22d37-e01f-4fa0-a440-c72585c7487f',
            'dashboard_enabled': False
        }
        with mock.patch('builtins.open', self.mock_open_ceph_all):
            data = export.export_ceph('dcn0', 'openstack',
                                      config_download_dir='/foo',
                                      mon_ips=['192.168.24.42'])
        self.assertEqual(data, expected)
        self.mock_open_ceph_all.assert_called_once_with(
            '/foo/dcn0/ceph-ansible/group_vars/all.yml', 'r')
