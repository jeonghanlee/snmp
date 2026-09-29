use strict;
use warnings;
use Digest::SHA;

my $digest = Digest::SHA->new(256);
for my $path (@ARGV) {
    open my $input, '<', $path or die "Cannot read worker source\n";
    binmode $input;
    $digest->add($path, "\0");
    $digest->addfile($input);
    close $input;
}
print '#define SNMP_WORKER_BUILD "', $digest->hexdigest, '"', "\n";
