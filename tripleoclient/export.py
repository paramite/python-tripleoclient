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


import logging
import os
import re
import yaml

from osc_lib.i18n import _

from tripleo_common.utils import plan as plan_utils
from tripleoclient import constants
from tripleoclient import utils as oooutils


LOG = logging.getLogger(__name__ + ".utils")


def export_passwords(heat, stack, excludes=True):
    """For each password, check if it's excluded, then check if there's a user
    defined value from parameter_defaults, and if not use the value from the
    generated passwords.
    :param heat: tht client
    :type heat: Client
    :param stack: stack name for password generator
    :type stack: string
    :param excludes: filter the passwords or not, defaults to `True`
    :type excludes: bool
    :returns: filtered password dictionary
    :rtype: dict
    """

    def exclude_password(password):
        for pattern in constants.EXPORT_PASSWORD_EXCLUDE_PATTERNS:
            if re.match(pattern, password, re.I):
                return True

    generated_passwords = plan_utils.generate_passwords(
        heat=heat, container=stack)

    filtered_passwords = generated_passwords.copy()

    if excludes:
        for password in generated_passwords:
            if exclude_password(password):
                filtered_passwords.pop(password, None)

    return filtered_passwords


def export_stack(heat, stack, should_filter=False,
                 config_download_dir=constants.DEFAULT_WORK_DIR):
    """Export stack information.
    Iterates over parameters selected for export and loads
    additional data from the referenced files.

    :param heat: tht client
    :type heat: Client
    :param stack: stack name for password generator
    :type stack: string
    :params should_filter:
        should the export only include values with keys
        defined in the 'filter' list. Defaults to `False`
    :type should_filter: bool
    :param config_download_dir:
        path to download directory,
        defaults to `constants.DEFAULT_WORK_DIR`
    :type config_download_dir: string

    :returns: data to export
    :rtype: dict

    The function detetermines what data to export using information,
    obtained from the preset `tripleoclient.constants.EXPORT_DATA` dictionary.
    parameter: Parameter to be exported
    file:   If file is specified it is taken as source instead of heat
            output. File is relative to <config-download-dir>/stack.
    filter: in case only specific settings should be
            exported from parameter data.
    """

    data = {}
    heat_stack = oooutils.get_stack(heat, stack)

    for export_key, export_param in constants.EXPORT_DATA.items():
        param = export_param["parameter"]

        if "file" in export_param:
            # get file data
            file = os.path.join(config_download_dir,
                                stack,
                                export_param["file"])
            export_data = oooutils.get_parameter_file(file)
        else:
            # get stack data
            export_data = oooutils.get_stack_output_item(
                            heat_stack, export_key)

        if export_data:
            # When we export information from a cell controller stack
            # we don't want to filter.
            if "filter" in export_param and should_filter:
                for filter_key in export_param["filter"]:
                    if filter_key in export_data:
                        element = {filter_key: export_data[filter_key]}
                        data.setdefault(param, {}).update(element)
            else:
                data[param] = export_data

        else:
            raise RuntimeError(
                "No data returned to export %s from." % param)

    # Check if AuthCloudName is in the stack environment, and if so add it to
    # the export data. Otherwise set it to the exported stack's name.
    auth_cloud_name = heat_stack.environment().get(
                        'parameter_defaults').get(
                            'AuthCloudName', None)
    if auth_cloud_name:
        data['AuthCloudName'] = auth_cloud_name
    else:
        data['AuthCloudName'] = stack

    return data


def export_ceph_net_key(stack, config_download_dir=constants.DEFAULT_WORK_DIR):
    file = os.path.join(config_download_dir, stack, "global_vars.yaml")
    with open(file, 'r') as ff:
        try:
            global_data = yaml.safe_load(ff)
        except yaml.MarkedYAMLError as e:
            LOG.error(
                _('Could not read file %s') % file)
            LOG.error(e)
    return str(global_data['service_net_map']['ceph_mon_network']) + '_ip'


def export_storage_ips(stack, config_download_dir=constants.DEFAULT_WORK_DIR,
                       ceph_net_key=''):
    if len(ceph_net_key) == 0:
        ceph_net_key = export_ceph_net_key(stack, config_download_dir)
    inventory_file = "ceph-ansible/inventory.yml"
    file = os.path.join(config_download_dir, stack, inventory_file)
    with open(file, 'r') as ff:
        try:
            inventory_data = yaml.safe_load(ff)
        except yaml.MarkedYAMLError as e:
            LOG.error(
                _('Could not read file %s') % file)
            LOG.error(e)
    mon_ips = []
    for mon_role in inventory_data['mons']['children'].keys():
        for hostname in inventory_data[mon_role]['hosts']:
            ip = inventory_data[mon_role]['hosts'][hostname][ceph_net_key]
            mon_ips.append(ip)

    return mon_ips


def export_ceph(stack, cephx,
                config_download_dir=constants.DEFAULT_WORK_DIR,
                mon_ips=[]):
    # Return a map of ceph data for a list item in CephExternalMultiConfig
    # by parsing files within the config_download_dir of a certain stack

    if len(mon_ips) == 0:
        mon_ips = export_storage_ips(stack, config_download_dir)

    # Use ceph-ansible group_vars/all.yml to get remaining values
    ceph_ansible_all = "ceph-ansible/group_vars/all.yml"
    file = os.path.join(config_download_dir, stack, ceph_ansible_all)
    with open(file, 'r') as ff:
        try:
            ceph_data = yaml.safe_load(ff)
        except yaml.MarkedYAMLError as e:
            LOG.error(
                _('Could not read file %s') % file)
            LOG.error(e)

    for key in ceph_data['keys']:
        if key['name'] == 'client.' + str(cephx):
            cephx_keys = [key]

    ceph_conf_overrides = {}
    ceph_conf_overrides['client'] = {}
    ceph_conf_overrides['client']['keyring'] = '/etc/ceph/' \
                                               + ceph_data['cluster'] \
                                               + '.client.' + cephx \
                                               + '.keyring'
    # Combine extracted data into one map to return
    data = {}
    data['external_cluster_mon_ips'] = str(','.join(mon_ips))
    data['keys'] = cephx_keys
    data['ceph_conf_overrides'] = ceph_conf_overrides
    data['cluster'] = ceph_data['cluster']
    data['fsid'] = ceph_data['fsid']
    data['dashboard_enabled'] = False

    return data


def export_overcloud(heat, stack, excludes, should_filter,
                     config_download_dir):
    data = export_passwords(heat, stack, excludes)
    data.update(export_stack(
        heat, stack, should_filter, config_download_dir))
    # do not add extra host entries for VIPs for stacks deployed off that
    # exported data, since it already contains those entries
    data.update({'AddVipsToEtcHosts': False})
    data = dict(parameter_defaults=data)
    return data
