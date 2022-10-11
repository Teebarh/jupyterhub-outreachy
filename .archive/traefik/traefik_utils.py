import time
import socket
import sys
import requests
import etcd3
from os.path import abspath, dirname, join
from subprocess import Popen

_ports = {
    "traefik": 8000,
    "default_backend": 9000,
    "first_backend": 9090,
    "second_backend": 9099,
}


def get_port(service_name):
    return _ports[service_name]


def is_open(ip, port):
    timeout = 1
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.shutdown(socket.SHUT_RDWR)
        return True
    except:
        return False
    finally:
        s.close()


def check_host_up(ip, port):
    """ Allow the service up to 2 sec to open connection on the
    designated port """
    up = False
    retry = 20  # iterations
    delay = 0.1  # 100 ms

    for i in range(retry):
        if is_open(ip, port):
            up = True
            break
        else:
            time.sleep(delay)
    return up


def traefik_routes_to_correct_backend(path, expected_port):
    """ Check if traefik followed the configuration and routed the
    request to the right backend """
    base_url = "http://localhost:" + str(get_port("traefik"))
    resp = requests.get(base_url + path)
    assert int(resp.text) == expected_port


def check_traefik_etcd_conf_ready():
    base_url = "http://localhost:" + str(get_port("traefik"))
    """ Allow traefik up to 10 sec to load its configuration from the
    etcd cluster """
    timeout = time.time() + 10
    ready = False
    t = 0.1
    while not ready and time.time() < timeout:
        resp = requests.get(base_url + "/api/providers/etcdv3")
        ready = resp.status_code == 200
        if not ready:
            t = min(2, t * 2)
            time.sleep(t)

    assert ready  # Check that we got here because we are ready


def get_backend_ports():
    default_backend_port = get_port("default_backend")
    first_backend_port = get_port("first_backend")
    second_backend_port = get_port("second_backend")
    return default_backend_port, first_backend_port, second_backend_port


def check_backends_up():
    """ Verify if the backends started listening on their designated
    ports """
    default_backend_port, first_backend_port, second_backend_port = (
        get_backend_ports()
    )
    assert check_host_up("localhost", default_backend_port) == True
    assert check_host_up("localhost", first_backend_port) == True
    assert check_host_up("localhost", second_backend_port) == True


def check_traefik_up():
    """ Verify if traefik started listening on its designated port """
    traefik_port = get_port("traefik")
    assert check_host_up("localhost", traefik_port) == True


def launch_backends():
    default_backend_port, first_backend_port, second_backend_port = (
        get_backend_ports()
    )
    dummy_server_path = abspath(join(dirname(__file__), "dummy_http_server.py"))

    default_backend = Popen(
        [sys.executable, dummy_server_path, str(default_backend_port)],
        stdout=None,
    )
    first_backend = Popen(
        [sys.executable, dummy_server_path, str(first_backend_port)],
        stdout=None,
    )
    second_backend = Popen(
        [sys.executable, dummy_server_path, str(second_backend_port)],
        stdout=None,
    )
    return default_backend, first_backend, second_backend


def launch_traefik_with_toml():
    traefik_port = get_port("traefik")
    config_file_path = abspath(join(dirname(__file__), "traefik.toml"))
    traefik = Popen(["traefik", "-c", config_file_path], stdout=None)
    return traefik


def launch_traefik_with_etcd():
    traefik_port = get_port("traefik")
    traefik = Popen(["traefik", "--etcd", "--etcd.useapiv3=true"], stdout=None)
    return traefik


def check_routing():
    default_backend_port, first_backend_port, second_backend_port = (
        get_backend_ports()
    )
    """ Send GET requests for resources on different paths and check
    they are routed based on their path-prefixes """
    traefik_routes_to_correct_backend("/otherthings", default_backend_port)
    traefik_routes_to_correct_backend("/user/somebody", default_backend_port)
    traefik_routes_to_correct_backend("/user/first", first_backend_port)
    traefik_routes_to_correct_backend("/user/second", second_backend_port)
    traefik_routes_to_correct_backend(
        "/user/first/otherthings", first_backend_port
    )
    traefik_routes_to_correct_backend(
        "/user/second/otherthings", second_backend_port
    )


def generate_traefik_toml():
    pass  # Not implemented

def create_etcd_config():
    etcd = etcd3.client(host='127.0.0.1', port=2379)

    etcd.put('/traefik/debug', 'true')
    etcd.put('/traefik/defaultentrypoints/0', 'http')
    etcd.put('/traefik/entrypoints/http/address', ':8000')
    etcd.put('/traefik/api/dashboard', 'true')
    etcd.put('/traefik/api/entrypoint', 'http')
    etcd.put('/traefik/loglevel', 'DEBUG')
    etcd.put('/traefik/backends/defaultbackend/servers/server1/url', 'http://127.0.0.1:9000')
    etcd.put('/traefik/backends/defaultbackend/servers/server1/weight', '1')
    etcd.put('/traefik/backends/userfirstbackend/servers/server1/url', 'http://127.0.0.1:9090')
    etcd.put('/traefik/backends/userfirstbackend/servers/server1/weight', '1')
    etcd.put('/traefik/backends/usersecondbackend/servers/server1/url', 'http://127.0.0.1:9099')
    etcd.put('/traefik/backends/usersecondbackend/servers/server1/weight', '1')
    etcd.put('/traefik/frontends/default/backend', 'defaultbackend')
    etcd.put('/traefik/frontends/default/routes/test_1/rule', 'PathPrefix:/')
    etcd.put('/traefik/frontends/userfirst/backend', 'userfirstbackend')
    etcd.put('/traefik/frontends/userfirst/routes/test/rule', 'PathPrefix:/user/first')
    etcd.put('/traefik/frontends/usersecond/backend', 'usersecondbackend')
    etcd.put('/traefik/frontends/usersecond/routes/test/rule', 'PathPrefix:/user/second')
    etcd.put('/traefik/etcd/endpoint', '127.0.0.1:2379')
    etcd.put('/traefik/etcd/prefix', '/traefik')
    etcd.put('/traefik/etcd/useapiv3', 'true')
    etcd.put('/traefik/etcd/watch', 'true')
