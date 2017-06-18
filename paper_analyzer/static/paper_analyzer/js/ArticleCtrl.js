ArticleCtrl = angular.module('pubAssistantClient').controller('ArticleCtrl',
 ['$scope', '$http', '$log', '$state', '$stateParams',
 function($scope, $http, $log, $state, $stateParams) {
    $scope.Shared = $scope.Shared || {
        articleText: '',
        articlePages: {},
        publicationPages: {},
        requestPending: false,
        requestError: false
    };
    $scope.page_size = 10;
    $scope.pages_fetch_range = 1;
    $scope.item_count = 0;

    $scope.searchArticles = function(page) {
        $scope.Shared.requestError = false;
        if ($scope.Shared.requestPending) return;
        if (typeof(page)==='undefined') page = 1;
        var startPage = Math.max(1, page - $scope.pages_fetch_range);
        var endPage = page + $scope.pages_fetch_range;
        var start = (startPage - 1) * $scope.page_size;
        if ($scope.item_count > 0) {
            end = Math.min(endPage * $scope.page_size - 1, $scope.item_count);
        } else {
            end = endPage * $scope.page_size - 1;
        }
        var headers = {'Range': 'items=' + start + '-' + end};
        var data = {'text': $scope.Shared.articleText};
        $scope.Shared.requestPending = true;
        $http.post(urls.searchArticlesUrl, data, {headers: headers}).then(
            function successCallback(response) {
                $scope.Shared.requestPending = false;
                $scope.Shared.requestError = false;
                var results = response.data;
                $scope.item_count = parseInt(response.headers('Content-Range').split('/')[1], 10);
                var start = parseInt(response.headers('Content-Range').split('-')[0].split(' ')[1], 10);
                var end = parseInt(response.headers('Content-Range').split('/')[0].split('-')[1], 10);
                var startPage = start / $scope.page_size + 1;
                var endPage = end / $scope.page_size;
                for (var i = 0; i < endPage - startPage; ++i) {
                    $scope.Shared.articlePages[startPage + i] = results.slice(i * $scope.page_size,
                                                                              (i + 1) * $scope.page_size);
                }
                $scope.results = $scope.Shared.articlePages[$scope.page];
                $scope.updatePagination();
            }, function failCallback(response) {
                $scope.Shared.requestPending = false;
                $scope.Shared.requestError = true;
            });
    }

    $scope.searchPublications = function(page) {
        $scope.Shared.requestError = false;
        if ($scope.Shared.requestPending) return;
        if (typeof(page)==='undefined') page = 1;
        var startPage = Math.max(1, page - $scope.pages_fetch_range);
        var endPage = page + $scope.pages_fetch_range;
        var start = (startPage - 1) * $scope.page_size;
        if ($scope.item_count > 0) {
            end = Math.min(endPage * $scope.page_size - 1, $scope.item_count);
        } else {
            end = endPage * $scope.page_size - 1;
        }
        var headers = {'Range': 'items=' + start + '-' + end};
        var data = {'text': $scope.Shared.articleText};
        $scope.Shared.requestPending = true;
        $http.post(urls.searchPublicationsUrl, data, {headers: headers}).then(
            function successCallback(response) {
                $scope.Shared.requestPending = false;
                $scope.Shared.requestError = false;
                $scope.item_count = parseInt(response.headers('Content-Range').split('/')[1], 10);
                var start = parseInt(response.headers('Content-Range').split('-')[0].split(' ')[1], 10);
                var end = parseInt(response.headers('Content-Range').split('/')[0].split('-')[1], 10);
                var startPage = start / $scope.page_size + 1;
                var endPage = end / $scope.page_size;
                for (var i = 0; i < endPage - startPage; ++i) {
                    $scope.Shared.publicationPages[startPage + i] = results.slice(i * $scope.page_size,
                                                                                  (i + 1) * $scope.page_size);
                }
                $scope.results = $scope.Shared.publicationPages[$scope.page];
                $scope.updatePagination();
                $scope.fetchRankings();
            }, function failCallback(response) {
                $scope.Shared.requestPending = false;
                $scope.Shared.requestError = true;
            });
    }

    $scope.updatePagination = function() {
        var last_page = ($scope.item_count == 0) ? 100 : Math.ceil($scope.item_count / $scope.page_size) - 1;
        var first = ($scope.page == 1) ? false : true;
        var previous = {page: $scope.page - 1, enabled: ($scope.page == 1) ? false : true};
        var next = {page: $scope.page + 1, enabled: ($scope.page == last_page) ? false : true};
        var start = Math.max($scope.page - 5, 1);
        var end = Math.min(start + 11, last_page);
        var more_left = {enabled: (start == 1) ? false : true, page_num: start - 1};
        var more_right = {enabled: (end == last_page) ? false : true, page_num: end + 1};
        var pages = [];
        for (i = start; i <=end; ++i) {
            var enabled = (i == $scope.page) ? false : true;
            pages.push({enabled: enabled, page_num: i});
        }
        $scope.pagination = {first: first, previous: previous, next: next,
            more_left:more_left, more_right:more_right, pages: pages};
    }

    $scope.fetchRankings = function() {
        function callBackCreator(i) {
            return function(response) {
                var rankings = response.data;
                $scope.results[i].rankings = {};
                for (j = 0; j < rankings.length; ++j) {
                    var ranking = rankings[j];
                    $scope.results[i].rankings[ranking.type] = rankings[j];
                }
            }
        }
        $log.debug('fetchRankings');
        for (i = 0; i < $scope.results.length; ++i) {
            params = {'id': $scope.results[i].id};
            $http.get(urls.journalRankingsUrl, {params: params}).then(
                callBackCreator(i), function failCallback(response) {
                    angular.noop();
                });
        }
    }

    if (Object.keys($scope.Shared.articleText).length == 0) {
//        on "refresh" or "back" go to first state
        $state.go('paper-analyzer.text');
    }

    if ($state.is('paper-analyzer.text')) {
        $scope.Shared.articlePages = {};
        $scope.Shared.publicationPages = {};
    }

    if ($state.is('paper-analyzer.articles')) {
        $scope.page = parseInt($stateParams.page, 10);
        if (!$scope.Shared.articlePages.hasOwnProperty($scope.page)) {
            $scope.searchArticles($scope.page);
        } else {
            $scope.results = $scope.Shared.articlePages[$scope.page];
            $scope.updatePagination();
        }
    }
    if ($state.is('paper-analyzer.journals')) {
        $scope.page = parseInt($stateParams.page, 10);
        if (!$scope.Shared.publicationPages.hasOwnProperty($scope.page)) {
            $scope.searchPublications($scope.page);
        } else {
            $scope.results = $scope.Shared.publicationPages[$scope.page];
            $scope.updatePagination();
            $scope.fetchRankings();
        }
    }

    $scope.gotoPage = function(page) {
        $state.go('.', {page: page});
    }
}]);