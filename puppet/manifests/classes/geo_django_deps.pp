# Install extra binary deps for GeoDjango
class geo_django_deps {
    package { "gdal-bin":
        ensure => installed,
        require => Class['python'];
    }

    package { "libproj-dev":
        ensure => installed;
    }
}
