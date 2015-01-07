import ApiHelper
import Log

import os
import re
import socket
import subprocess
import tempfile
import time
import xml.dom.minidom
import xml.sax.saxutils


def runlocal(cmd, shell=False, canfail=False):
    Log.debug("Running: %s" % (cmd))
    process = subprocess.Popen(cmd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               stdin=subprocess.PIPE,
                               shell=shell)
    stdout, stderr = process.communicate('')
    rc = process.returncode
    Log.debug("Command %s exited with rc %d: Stdout: %s Stderr: %s" %
              (cmd, rc, stdout, stderr))
    if rc != 0 and not canfail:
        raise(Exception("Command failed"))
    return (rc, stdout, stderr)


def converttoxml(node, parentelement=None, dom=None):
    if not dom or not parentelement:
        dom = xml.dom.minidom.Document()
        converttoxml(node, parentelement=dom, dom=dom)
        return dom.toxml()

    if type(node) == type([]):
        for item in node:
            converttoxml(item, parentelement=parentelement, dom=dom)
    elif type(node) in [type(''), type(1), type(1.1)]:
        textnode = dom.createTextNode(xml.sax.saxutils.escape(str(node)))
        parentelement.appendChild(textnode)
    elif type(node) == type({}):
        for key, value in node.iteritems():
            element = dom.createElement(xml.sax.saxutils.escape(key))
            parentelement.appendChild(element)
            converttoxml(value, parentelement=element, dom=dom)


def create_idrsa():
    (filehandle, idrsafile) = tempfile.mkstemp()
    os.remove(idrsafile)
    cmd = ['ssh-keygen', '-f', idrsafile, '-N', '']
    runlocal(cmd)
    idrsapriv = read_file("%s" % (idrsafile))
    idrsapub = read_file("%s.pub" % (idrsafile))
    os.remove(idrsafile)
    return (idrsapriv, idrsapub)


def read_file(filepath):
    filehandle = open(filepath, 'r')
    content = filehandle.read()
    filehandle.close()
    return content


def write_file(filepath, content):
    filehandle = open(filepath, "w+")
    filehandle.write(content)
    filehandle.close()
    os.chmod(filepath, 0600)


def ensure_idrsa(session, idrsafilename):
    neednewfile = False
    if os.path.exists(idrsafilename):
        mtime = os.path.getmtime(idrsafilename)
        if time.time() - mtime > 60:
            neednewfile = True
    else:
        neednewfile = True
    if neednewfile:
        write_file(idrsafilename, ApiHelper.get_idrsa_secret_private(session))


def execute_ssh(session, host, cmd):
    idrsafilename = '/tmp/xscontainer-idrsa'
    ensure_idrsa(session, idrsafilename)
    cmd = ['ssh', '-o', 'UserKnownHostsFile=/dev/null',
           '-o', 'StrictHostKeyChecking=no',
           '-o', 'PasswordAuthentication=no',
           '-o', 'LogLevel=quiet',
           '-o', 'ConnectTimeout=10',
           '-i', idrsafilename, 'core@%s' % (host)] + cmd
    stdout = runlocal(cmd)[1]
    return str(stdout)


def test_connection(ip, port):
    try:
        asocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Allow the connection to block for 2 seconds
        asocket.settimeout(2)
        asocket.connect((ip, port))
        asocket.close()
        return True
    except:
        return False


def get_suitable_vm_ip(session, vmuuid):
    ips = ApiHelper.get_vm_ips(session, vmuuid)
    stage1filteredips = []
    for network, ip in ips.iteritems():
        if ':' not in ip:
            # if ipv4
            if ip.startswith('169.254.'):
                # Prefer host internal network
                stage1filteredips.insert(0, ip)
            else:
                stage1filteredips.append(ip)
    for ip in stage1filteredips:
        if test_connection(ip, 22):
            return ip
    raise Exception("No valid IP found for vmuuid %s" % (vmuuid))
