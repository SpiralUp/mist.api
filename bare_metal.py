import sys
import socket

import httplib
from libcloud.compute.types import NodeState
from libcloud.compute.base import Node


VALID_RESPONSE_CODES = [httplib.OK, httplib.ACCEPTED, httplib.CREATED,
                        httplib.NO_CONTENT]

NODE_STATE_MAP = {
    'on': NodeState.RUNNING,
    'off': NodeState.UNKNOWN,
    'unknown': NodeState.UNKNOWN,
}

class BareMetalDriver(object):
    """
    Bare Metal Driver class.

    """
    type = 'bare_metal'
    name = 'BareMetal'

    def __init__(self, list_of_machines):
        self.machines = list_of_machines

    def __repr__(self):
        return ('<BareMetalDriver>')

    def list_nodes(self):
        nodes = [self._to_node(machine_id, machine)
                 for machine_id, machine in self.machines.items()]
        return nodes

    def list_sizes(self):
        return []

    def list_locations(self):
        return []

    def list_images(self):
        return []

    def reboot_node(self, node):
        result = httplib.OK
        return result in VALID_RESPONSE_CODES

    def ex_stop_node(self, node):
        result = httplib.OK
        return result in VALID_RESPONSE_CODES

    def _to_node(self, machine_id, machine):
        state = self.check_host(machine.dns_name, machine.ssh_port)

        node = Node(id=machine_id, name=machine.name, state=state,
                    public_ips=machine.public_ips, private_ips=[],
                    driver=self, extra={})
        return node

    def check_host(self, hostname, port=22):
        "Perform a check if port is open"
        #FIXME: needs more thinking here!!!
        socket.setdefaulttimeout(5)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((hostname, port))
            s.shutdown(2)
            state = NODE_STATE_MAP['on']
        except:
            state = NODE_STATE_MAP['off']
        return state
