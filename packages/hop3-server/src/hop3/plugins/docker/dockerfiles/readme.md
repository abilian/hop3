# Notes

Various Dockerfiles depending on the project profile.

Probably too simplistic. The static dockerfiles are not flexible enough to handle all the different project profiles and their specific requirements, and will need to be templated.

An alternative would be to have a build agent, like in the Nua project, and let the build agent run the build, using metadata from the project profile to take the right decisions.
