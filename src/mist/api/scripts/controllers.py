import os
import yaml
import random
import logging
import mist.api.shell
from io import StringIO
from mist.api.exceptions import BadRequestError
from mist.api.exceptions import ScriptFormatError
from mist.api.scripts.base import BaseScriptController
from yaml.parser import ParserError as YamlParserError
from yaml.scanner import ScannerError as YamlScannerError

from mist.api.monitoring.methods import associate_metric


log = logging.getLogger(__name__)


class AnsibleScriptController(BaseScriptController):

    def _preparse_file(self):
        if self.script.location.type == 'inline':
            try:
                yaml.load(self.script.location.source_code)
            except (YamlParserError, YamlScannerError):
                raise ScriptFormatError()

    def run_script(self, shell, params=None, job_id=None):
        path, params = super(
            AnsibleScriptController, self).run_script(shell, params=params,
                                                      job_id=job_id)
        return path, params


class ExecutableScriptController(BaseScriptController):

    def _preparse_file(self):
        if self.script.location.type == 'inline':
            if self.script.location.source_code:
                if not self.script.location.source_code.startswith('#!'):
                    raise BadRequestError(
                        "'script' must start with a hashbang/shebang ('#!')."
                    )
            else:
                raise BadRequestError("for inline script you must provide "
                                      "source code")


class TelegrafScriptController(BaseScriptController):

    # FIXME Rename methods, since telegraf can run any sort of executable,
    # not just python scripts.

    def deploy_python_plugin(self, machine):
        # Paths for testing and deployment.
        conf_dir = '/opt/mistio/mist-telegraf/custom'
        test_dir = '/tmp/mist-telegraf-plugin-%d' % random.randrange(2 ** 20)
        test_conf = os.path.join(test_dir, 'exec.conf')
        test_plugin = os.path.join(test_dir, self.script.name)

        # Test configuration to ensure telegraf can load the executable.
        exec_conf = """
[[inputs.exec]]
  commands = ['%s']
  data_format = 'influx'
""" % (test_plugin)

        # Code to run in order to test the script's execution. Firstly, the
        # script is run by itself to make sure it does not throw any errors
        # and then it is loaded by telegraf using the exec plugin to verify
        # the computed series can be parsed.
        test_code = """
$(command -v sudo) chmod +x %s && \
$(command -v sudo) %s && \
$(command -v sudo) /opt/mistio/telegraf/usr/bin/telegraf -test -config %s
""" % (test_plugin, test_plugin, test_conf)

        # Initialize SSH connection.
        shell = mist.api.shell.Shell(machine.ctl.get_host())
        key_id, ssh_user = shell.autoconfigure(self.script.owner,
                                               machine.cloud.id,
                                               machine.id)
        sftp = shell.ssh.open_sftp()

        # Create the test directory and the directory to store custom scripts,
        # if missing.
        retval, stdout = shell.command(
            'mkdir -p %s && [ -d %s ] || mkdir %s' % (test_dir,
                                                      conf_dir, conf_dir)
        )
        if retval:
            raise BadRequestError('Failed to init working dir: %s' % stdout)

        # Deploy the test configuration and the plugin.
        sftp.putfo(StringIO(exec_conf), test_conf)
        sftp.putfo(StringIO(self.script.location.source_code), test_plugin)

        # Run the test code to verify the plugin is working.
        retval, test_out, test_err = shell.command(test_code, pty=False)
        stdout += test_out
        if test_err:
            raise BadRequestError(
                "Test of read() function failed. Ensure the script's output "
                "is in the correct format for telegraf to parse. Expected "
                "format is 'measurement_name field1=val1[,field2=val2,...]'."
                "Error: %s" % test_err)

        # After the test/dry run, parse the series from stdout to gather
        # the measurement's name, tags, and values.
        series = []
        for line in test_out.splitlines():
            if line.startswith('> '):
                line = line[2:]
                measurement_and_tags, values, timestamp = line.split()
                measurement, tags = measurement_and_tags.split(',', 1)
                series.append((measurement, tags, values))
        if not series:
            raise BadRequestError('No computed series found in stdout')

        # Construct a list of `metric_id`s. All `metric_id`s are in the form:
        # `<measurement>.<column>`. The aforementioned notation does not hold
        # for the Graphite-based system, if the column name is "value", since
        # in that case Graphite stores the series at the top level and not in
        # a subdirectory, thus the measurement name suffices to query for the
        # specified metric.
        metrics = []
        for s in series:
            measurement = s[0]
            values_list = s[2].split(',')
            for value in values_list:
                metric = measurement
                column = value.split('=')[0]
                if not (machine.monitoring.method == 'telegraf-graphite' and
                        column == 'value'):
                    metric += '.' + column
                if metric in machine.monitoring.metrics:
                    raise BadRequestError('Metric %s already exists' % metric)
                metrics.append(metric)

        # Copy the plugin to the proper directory in order to be picked up by
        # telegraf.
        retval, stdout = shell.command('$(command -v sudo) '
                                       'cp %s %s' % (test_plugin, conf_dir))
        if retval:
            raise BadRequestError('Failed to deploy plugin: %s' % stdout)

        # Clean up working tmp dir.
        retval, stdout = shell.command('$(command -v sudo) '
                                       'rm -rf %s' % test_dir)
        if retval:
            log.error('Failed to clean up working dir: %s', stdout)

        # Close SSH connection.
        shell.disconnect()

        return {'metrics': metrics, 'stdout': stdout}

    def deploy_and_assoc_python_plugin_from_script(self, machine):
        ret = self.deploy_python_plugin(machine)
        for metric_id in ret['metrics']:
            if self.script.extra.get('value_type') == 'derive':
                metric_id = 'derivative(%s)' % metric_id
            associate_metric(
                machine, metric_id,
                name=self.script.extra.get('value_name') or self.script.name,
                unit=self.script.extra.get('value_unit', ''),
            )
        return ret
