#!/bin/bash -e

beforeCommand=$1
shouldPublish=$2

runner () {
    echo "🟡 starting $@"
    if $@; then
        echo "🟢 $@ passed"
    else
        echo "🔴 $@ failed"
        exit 1
    fi
}

configure_git() {
    if [[ -n "$GITHUB_WORKSPACE" ]]; then
        git config --global --add safe.directory "$GITHUB_WORKSPACE"
    fi
    git config --global user.name "${GITHUB_ACTOR}"
    git config --global user.email 'autobump@users.noreply.github.com'
}

check_uncommitted_changes() {
    if [ -n "$(git status --porcelain)" ]; then
        echo "🔴 There are uncommitted changes, exiting"
        exit 1
    fi
}

run_hatch_command() {
    export INPUT_REPOSITORY_URL=https://pypi.org
    export HATCH_INDEX_USER=__token__
    export HATCH_INDEX_AUTH="$(python /app/oidc-exchange.py)"
    echo "🟢 HATCH_INDEX_AUTH=$HATCH_INDEX_AUTH"
    runner hatch run "$beforeCommand"
    git reset --hard
    echo "🟢 beforeCommand success"
}

bump_version() {
    local VERSION
    VERSION=$(hatch version)
    case $GITHUB_REF in
        'refs/heads/main'|'refs/heads/master'|'refs/heads/release')
            hatch version release
            ;;
        'refs/heads/alpha')
            if [[ "$VERSION" == *"a"* ]]; then
                hatch version alpha
            else
                hatch version minor,alpha
            fi
            ;;
        'refs/heads/beta')
            if [[ "$VERSION" == *"b"* ]]; then
                hatch version beta
            else
                hatch version minor,beta
            fi
            ;;
        'refs/heads/dev'|'refs/heads/develop')
            if [[ "$VERSION" == *"dev"* ]]; then
                hatch version dev
            else
                hatch version minor,dev
            fi
            ;;
        'refs/heads/patch')
            if [[ "$VERSION" == *"dev"* ]]; then
                hatch version dev
            else
                hatch version patch,dev
            fi
            ;;
        *)
            echo "🔵 Skipped Version Bump"
            ;;
    esac
}

publish_version() {
    local VERSION NEW_VERSION
    VERSION=$(hatch version)
    NEW_VERSION=$(hatch version)
    if [ "$VERSION" != "$NEW_VERSION" ] && [ "$shouldPublish" == true ]; then
        echo "🟢 Success: bump version: $VERSION → $NEW_VERSION"
        git add .
        git commit -m "Bump version: $VERSION → $NEW_VERSION"
        git tag "v$NEW_VERSION"
        git remote -v
        echo "🟢 Success version push"
        runner hatch build
        runner hatch publish
        git push
        git push --tags
        runner gh release create "v$NEW_VERSION" -F CHANGELOG.md dist/*.whl dist/*.tar.gz
        echo "release is complete"
    else
        echo "🔵 Skipped Publish"
    fi
}

main() {
    configure_git
    check_uncommitted_changes
    run_hatch_command
    bump_version
    publish_version
}

main
