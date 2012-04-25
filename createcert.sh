#!/bin/sh

echodo()
{
        echo "${@}"
                (${@})
}

yearmon()
{
        date '+%Y%m%d'
}

fqdn()
{
        (nslookup ${1} 2>&1 && echo Name ${1}) \
                    | tail -3 | grep Name| sed -e 's,.*e:[ \t]*,,'
}

C=AU
ST=SA
L=Adelaide
O=codenes
OU=nes
HOST=${1:-`hostname`}
DATE=`yearmon`
CN=`fqdn $HOST`

csr="${HOST}.csr"
key="${HOST}.key"
cert="${HOST}.cert"

# Create the certificate signing request
openssl req -new -passin pass:password -passout pass:password -out $csr <<EOF
${C}
${ST}
${L}
${O}
${OU}
${CN}
$USER@${CN}
.
.
EOF
echo ""

[ -f ${csr} ] && echodo openssl req -text -noout -in ${csr}
echo ""

# Create the Key
openssl rsa -in privkey.pem -passin pass:password -passout pass:password -out ${key}

# Create the Certificate
openssl x509 -in ${csr} -out ${cert} -req -signkey ${key} -days 1000

