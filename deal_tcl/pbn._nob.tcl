proc write_deal {} {
  foreach hand {north east south west} {
    set fmt($hand) "[$hand spades].[$hand hearts].[$hand diamonds].[$hand clubs]"
  }
  puts "[format {"N:%s %s %s %s"} $fmt(north) $fmt(east) $fmt(south) $fmt(west)]"
}
