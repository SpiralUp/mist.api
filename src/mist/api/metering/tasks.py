import logging
import requests
import datetime

from mist.api import config
from mist.api.celery_app import app
from mist.api.rules.models import Rule
from mist.api.machines.models import Machine
from mist.api.monitoring.methods import get_stats


log = logging.getLogger(__name__)


def _skip_metering(machine):
    # Prevents counting the vCPUs of docker containers and KVM guests.
    if machine.cloud.ctl.provider == 'docker':
        if machine.machine_type != 'container-host':
            return True
    if machine.cloud.ctl.provider == 'libvirt':
        if machine.extra.get('tags', {}).get('type') != 'hypervisor':
            return True
    return False


@app.task
def find_machine_cores(machine_id):
    """Decide on the number of vCPUs for all machines"""

    def _get_cores_from_unix(machine):
        return machine.ssh_probe.cores if machine.ssh_probe else 0

    def _get_cores_from_tsdb(machine):
        if machine.monitoring.hasmonitoring:
            if machine.monitoring.method.endswith('graphite'):
                metric = 'cpu.*.idle'
            elif machine.monitoring.method.endswith('tsfdb'):
                metric = ('fetch(\"{id}.cpu.*\d.usage_idle\"' +
                          ', start=\"{start}\", stop=\"{stop}\"' +
                          ', step=\"{step}\")')
            else:
                metric = 'cpu.cpu=/cpu\d/.usage_idle'
            return len(get_stats(machine, start='-60sec', metrics=[metric]))
        return 0

    def _get_cores_from_machine_extra(machine):
        try:
            return int(machine.extra.get('cpus', 0))
        except ValueError:
            return 0

    def _get_cores_from_libcloud_size(machine):
        return machine.size.cpus if machine.size else 0

    try:
        machine = Machine.objects.get(id=machine_id)
        machine.cores = (
            _get_cores_from_unix(machine) or
            _get_cores_from_tsdb(machine) or
            _get_cores_from_machine_extra(machine) or
            _get_cores_from_libcloud_size(machine)
        )
        machine.save()
    except Exception as exc:
        log.error('Failed to get cores of machine %s: %r', machine.id, exc)


@app.task
def push_metering_info(owner_id):
    """Collect and push new metering data to InfluxDB"""
    now = datetime.datetime.utcnow()
    metering = {}

    # Base InfluxDB URL.
    url = config.INFLUX['host']

    # Create database for storing metering data, if missing.
    db = requests.post('%s/query?q=CREATE DATABASE metering' % url)
    if not db.ok:
        raise Exception(db.content)

    # CPUs
    for machine in Machine.objects(owner=owner_id, last_seen__gte=now.date()):
        metering.setdefault(
            owner_id,
            dict.fromkeys(('cores', 'checks', 'datapoints'), 0)
        )
        try:
            if _skip_metering(machine):
                continue
            metering[owner_id]['cores'] += machine.cores or 0
        except Exception as exc:
            log.error('Failed upon cores metering of %s: %r', machine.id, exc)

    # Checks
    for rule in Rule.objects(owner_id=owner_id):
        try:
            metering[rule.owner_id]['checks'] += rule.total_check_count
        except Exception as exc:
            log.error('Failed upon checks metering of %s: %r', rule.id, exc)

    # Datapoints
    query = ('fetch("*.dp.gocky.*counter", start="-30m", stop="", step="")')
    try:
        result = requests.get(
            "%s/v1/metering/datapoints?query=%s" % (config.TSFDB_URI, query),
            headers={'x-org-id': owner_id},
            timeout=15
        )
        if not result.ok:
            raise Exception('Could not fetch gocky datapoints counters from TSFDB')
        result = result.json()
        for _, datapoints in result['series'].items():
            if datapoints:
                metering[owner_id]['datapoints'] += max(datapoints,key=lambda x: x[0])[0]
    except Exception as exc:
        log.error('Failed upon datapoints metering: %r', exc)

    # Assemble points.
    points = []
    for owner, counters in metering.items():
        value = ','.join(['%s=%s' % (k, v) for k, v in counters.items()])
        point = 'usage,machine_id=%s %s' % (owner, value)
        points.append(point)

    # Write metering data.
    data = '\n'.join(points)
    write = requests.post(
            "%s/v1/metering/datapoints" % (config.TSFDB_URI),
            headers={'x-org-id': owner_id}, data=data,
            timeout=15
        )
    if not write.ok:
        log.error('Failed to write metering data: %s', write.text)
