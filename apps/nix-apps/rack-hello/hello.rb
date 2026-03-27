# frozen_string_literal: true

class HelloWorld
  def call(env)
    [200, { 'content-type' => 'text/plain' }, ['Hello World, from Rack via Nix!']]
  end
end
