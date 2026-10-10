package authz

default allow := false

allow if {
  input.request.method == "GET"
  input.request.path == "/health"
}

allow if {
  input.user.authenticated == true
}
